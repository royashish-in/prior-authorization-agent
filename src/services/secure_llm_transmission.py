"""
Secure LLM Data Transmission Service

Provides secure, encrypted data transmission for external LLM calls with
comprehensive security measures including TLS, request signing, and
audit logging for HIPAA compliance.
"""

import asyncio
import logging
import json
import hashlib
import hmac
import time
import uuid
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import ssl
import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import base64
import os

from ..core.encryption import get_phi_encryption
from ..core.secrets import llm_secrets_manager
from ..audit.logger import get_audit_logger
from ..audit.models import AuditEventType, SecurityLevel
from .huggingface_client import HuggingFaceRequest, HuggingFaceResponse


class TransmissionSecurityLevel(str, Enum):
    """Security levels for LLM data transmission."""
    STANDARD = "standard"  # TLS only
    ENHANCED = "enhanced"  # TLS + request signing
    MAXIMUM = "maximum"    # TLS + request signing + payload encryption


class TransmissionMethod(str, Enum):
    """Methods for secure transmission."""
    HTTPS_TLS = "https_tls"
    MUTUAL_TLS = "mutual_tls"
    VPN_TUNNEL = "vpn_tunnel"
    ON_PREMISES = "on_premises"


@dataclass
class SecurityHeaders:
    """Security headers for LLM requests."""
    request_id: str
    timestamp: str
    signature: str
    content_hash: str
    encryption_method: Optional[str] = None
    key_id: Optional[str] = None


@dataclass
class EncryptedPayload:
    """Encrypted payload for secure transmission."""
    encrypted_data: str
    encryption_method: str
    key_id: str
    iv: str
    auth_tag: Optional[str] = None


@dataclass
class SecureTransmissionRequest:
    """Secure transmission request wrapper."""
    request_id: str
    original_request: HuggingFaceRequest
    security_level: TransmissionSecurityLevel
    transmission_method: TransmissionMethod
    encrypted_payload: Optional[EncryptedPayload] = None
    security_headers: Optional[SecurityHeaders] = None
    phi_involved: bool = False
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class SecureTransmissionResponse:
    """Secure transmission response wrapper."""
    request_id: str
    original_response: HuggingFaceResponse
    security_validated: bool
    decryption_successful: bool
    transmission_time_ms: float
    security_level_used: TransmissionSecurityLevel
    audit_trail: List[str] = field(default_factory=list)


class RequestSigner:
    """Signs requests for authentication and integrity verification."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.RequestSigner")
        self._signing_key = self._get_or_generate_signing_key()
    
    def _get_or_generate_signing_key(self) -> bytes:
        """Get or generate signing key for request authentication."""
        # In production, this should be stored securely (HSM, Key Vault, etc.)
        signing_key = os.getenv("LLM_REQUEST_SIGNING_KEY")
        
        if not signing_key:
            # Generate a new key (in production, this should be done once and stored securely)
            signing_key = base64.b64encode(os.urandom(32)).decode()
            self.logger.warning("Generated new signing key - store this securely in production")
        
        return base64.b64decode(signing_key)
    
    def sign_request(
        self,
        request_id: str,
        payload: str,
        timestamp: str
    ) -> Tuple[str, str]:
        """Sign a request and return signature and content hash."""
        # Create content hash
        content_hash = hashlib.sha256(payload.encode()).hexdigest()
        
        # Create signature payload
        signature_payload = f"{request_id}:{timestamp}:{content_hash}"
        
        # Sign with HMAC-SHA256
        signature = hmac.new(
            self._signing_key,
            signature_payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return signature, content_hash
    
    def verify_signature(
        self,
        request_id: str,
        payload: str,
        timestamp: str,
        signature: str,
        content_hash: str
    ) -> bool:
        """Verify request signature."""
        try:
            # Verify content hash
            expected_hash = hashlib.sha256(payload.encode()).hexdigest()
            if not hmac.compare_digest(content_hash, expected_hash):
                return False
            
            # Verify signature
            signature_payload = f"{request_id}:{timestamp}:{content_hash}"
            expected_signature = hmac.new(
                self._signing_key,
                signature_payload.encode(),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(signature, expected_signature)
            
        except Exception as e:
            self.logger.error(f"Signature verification failed: {str(e)}")
            return False


class PayloadEncryptor:
    """Encrypts payloads for maximum security transmission."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.PayloadEncryptor")
        self.phi_encryption = get_phi_encryption()
    
    def encrypt_payload(
        self,
        payload: str,
        key_id: Optional[str] = None
    ) -> EncryptedPayload:
        """Encrypt payload using AES-256-GCM."""
        try:
            # Generate encryption key and IV
            encryption_key = os.urandom(32)  # AES-256
            iv = os.urandom(12)  # GCM recommended IV size
            
            # Create cipher
            cipher = Cipher(
                algorithms.AES(encryption_key),
                modes.GCM(iv),
                backend=default_backend()
            )
            encryptor = cipher.encryptor()
            
            # Encrypt payload
            ciphertext = encryptor.update(payload.encode()) + encryptor.finalize()
            
            # Get authentication tag
            auth_tag = encryptor.tag
            
            # Encrypt the encryption key with PHI encryption
            encrypted_key = self.phi_encryption.encrypt(base64.b64encode(encryption_key).decode())
            
            return EncryptedPayload(
                encrypted_data=base64.b64encode(ciphertext).decode(),
                encryption_method="AES-256-GCM",
                key_id=key_id or str(uuid.uuid4()),
                iv=base64.b64encode(iv).decode(),
                auth_tag=base64.b64encode(auth_tag).decode()
            )
            
        except Exception as e:
            self.logger.error(f"Payload encryption failed: {str(e)}")
            raise
    
    def decrypt_payload(
        self,
        encrypted_payload: EncryptedPayload
    ) -> str:
        """Decrypt payload."""
        try:
            # Decrypt the encryption key
            encrypted_key_bytes = self.phi_encryption.decrypt(encrypted_payload.key_id)
            encryption_key = base64.b64decode(encrypted_key_bytes)
            
            # Decode components
            ciphertext = base64.b64decode(encrypted_payload.encrypted_data)
            iv = base64.b64decode(encrypted_payload.iv)
            auth_tag = base64.b64decode(encrypted_payload.auth_tag) if encrypted_payload.auth_tag else None
            
            # Create cipher
            cipher = Cipher(
                algorithms.AES(encryption_key),
                modes.GCM(iv, auth_tag),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            
            # Decrypt payload
            plaintext = decryptor.update(ciphertext) + decryptor.finalize()
            
            return plaintext.decode()
            
        except Exception as e:
            self.logger.error(f"Payload decryption failed: {str(e)}")
            raise


class SecureLLMTransmissionService:
    """Main service for secure LLM data transmission."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.request_signer = RequestSigner()
        self.payload_encryptor = PayloadEncryptor()
        self.audit_logger = get_audit_logger()
        self._http_client: Optional[httpx.AsyncClient] = None
        self._ssl_context: Optional[ssl.SSLContext] = None
    
    async def initialize(self):
        """Initialize the secure transmission service."""
        self.logger.info("Initializing Secure LLM Transmission Service")
        
        # Create SSL context with enhanced security
        self._ssl_context = self._create_secure_ssl_context()
        
        # Initialize HTTP client with security settings
        timeout = httpx.Timeout(30.0)  # Configurable timeout
        limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)
        
        self._http_client = httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            verify=self._ssl_context,
            headers=self._get_security_headers()
        )
        
        self.logger.info("Secure LLM Transmission Service initialized")
    
    async def shutdown(self):
        """Shutdown the service."""
        if self._http_client:
            await self._http_client.aclose()
        self.logger.info("Secure LLM Transmission Service shutdown")
    
    def _create_secure_ssl_context(self) -> ssl.SSLContext:
        """Create secure SSL context with enhanced settings."""
        context = ssl.create_default_context()
        
        # Enhanced security settings
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        
        # Load client certificates if available (for mutual TLS)
        client_cert_path = os.getenv("LLM_CLIENT_CERT_PATH")
        client_key_path = os.getenv("LLM_CLIENT_KEY_PATH")
        
        if client_cert_path and client_key_path:
            try:
                context.load_cert_chain(client_cert_path, client_key_path)
                self.logger.info("Client certificates loaded for mutual TLS")
            except Exception as e:
                self.logger.warning(f"Failed to load client certificates: {str(e)}")
        
        return context
    
    def _get_security_headers(self) -> Dict[str, str]:
        """Get default security headers."""
        return {
            "User-Agent": "PriorAuthAgent-Secure/1.0",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains"
        }
    
    async def secure_transmit(
        self,
        url: str,
        request: HuggingFaceRequest,
        security_level: TransmissionSecurityLevel = TransmissionSecurityLevel.ENHANCED,
        phi_involved: bool = False
    ) -> SecureTransmissionResponse:
        """Securely transmit request to LLM service."""
        request_id = str(uuid.uuid4())
        start_time = datetime.now()
        
        try:
            # Create secure transmission request
            secure_request = SecureTransmissionRequest(
                request_id=request_id,
                original_request=request,
                security_level=security_level,
                transmission_method=TransmissionMethod.HTTPS_TLS,
                phi_involved=phi_involved
            )
            
            # Log transmission start
            self._log_transmission_event(
                "transmission_start",
                secure_request,
                {"url": url, "security_level": security_level.value}
            )
            
            # Prepare secure payload
            prepared_request = await self._prepare_secure_request(secure_request)
            
            # Transmit request
            response = await self._transmit_request(url, prepared_request)
            
            # Process response
            secure_response = await self._process_secure_response(
                request_id, response, security_level, start_time
            )
            
            # Log transmission completion
            self._log_transmission_event(
                "transmission_complete",
                secure_request,
                {
                    "success": secure_response.original_response.success,
                    "transmission_time_ms": secure_response.transmission_time_ms,
                    "security_validated": secure_response.security_validated
                }
            )
            
            return secure_response
            
        except Exception as e:
            transmission_time = (datetime.now() - start_time).total_seconds() * 1000
            
            # Log transmission failure
            self._log_transmission_event(
                "transmission_failed",
                SecureTransmissionRequest(
                    request_id=request_id,
                    original_request=request,
                    security_level=security_level,
                    transmission_method=TransmissionMethod.HTTPS_TLS,
                    phi_involved=phi_involved
                ),
                {"error": str(e), "transmission_time_ms": transmission_time}
            )
            
            # Return error response
            return SecureTransmissionResponse(
                request_id=request_id,
                original_response=HuggingFaceResponse(
                    model_id="unknown",
                    response_data=None,
                    processing_time_ms=transmission_time,
                    success=False,
                    error_message=f"Secure transmission failed: {str(e)}"
                ),
                security_validated=False,
                decryption_successful=False,
                transmission_time_ms=transmission_time,
                security_level_used=security_level,
                audit_trail=[f"Transmission failed: {str(e)}"]
            )
    
    async def _prepare_secure_request(
        self,
        secure_request: SecureTransmissionRequest
    ) -> Dict[str, Any]:
        """Prepare request with appropriate security measures."""
        # Convert request to JSON
        payload = json.dumps({
            "inputs": secure_request.original_request.inputs,
            "parameters": secure_request.original_request.parameters or {},
            "options": secure_request.original_request.options or {}
        })
        
        timestamp = str(int(time.time()))
        
        # Apply security based on level
        if secure_request.security_level == TransmissionSecurityLevel.MAXIMUM:
            # Encrypt payload
            encrypted_payload = self.payload_encryptor.encrypt_payload(payload)
            secure_request.encrypted_payload = encrypted_payload
            
            # Use encrypted payload for transmission
            transmission_payload = json.dumps({
                "encrypted_data": encrypted_payload.encrypted_data,
                "encryption_method": encrypted_payload.encryption_method,
                "key_id": encrypted_payload.key_id,
                "iv": encrypted_payload.iv,
                "auth_tag": encrypted_payload.auth_tag
            })
        else:
            transmission_payload = payload
        
        # Sign request (for enhanced and maximum security)
        if secure_request.security_level in [TransmissionSecurityLevel.ENHANCED, TransmissionSecurityLevel.MAXIMUM]:
            signature, content_hash = self.request_signer.sign_request(
                secure_request.request_id,
                transmission_payload,
                timestamp
            )
            
            secure_request.security_headers = SecurityHeaders(
                request_id=secure_request.request_id,
                timestamp=timestamp,
                signature=signature,
                content_hash=content_hash,
                encryption_method=secure_request.encrypted_payload.encryption_method if secure_request.encrypted_payload else None,
                key_id=secure_request.encrypted_payload.key_id if secure_request.encrypted_payload else None
            )
        
        # Prepare final request
        headers = {}
        if secure_request.security_headers:
            headers.update({
                "X-Request-ID": secure_request.security_headers.request_id,
                "X-Timestamp": secure_request.security_headers.timestamp,
                "X-Signature": secure_request.security_headers.signature,
                "X-Content-Hash": secure_request.security_headers.content_hash
            })
            
            if secure_request.security_headers.encryption_method:
                headers["X-Encryption-Method"] = secure_request.security_headers.encryption_method
                headers["X-Key-ID"] = secure_request.security_headers.key_id
        
        # Add PHI indicator
        if secure_request.phi_involved:
            headers["X-PHI-Involved"] = "true"
        
        return {
            "payload": transmission_payload,
            "headers": headers
        }
    
    async def _transmit_request(
        self,
        url: str,
        prepared_request: Dict[str, Any]
    ) -> httpx.Response:
        """Transmit the prepared request."""
        if not self._http_client:
            raise RuntimeError("HTTP client not initialized")
        
        # Add authentication headers
        headers = prepared_request["headers"].copy()
        
        # Add Hugging Face API token if available
        hf_token = llm_secrets_manager.get_huggingface_token()
        if hf_token:
            headers["Authorization"] = f"Bearer {hf_token}"
        
        headers["Content-Type"] = "application/json"
        
        # Make request with enhanced security
        response = await self._http_client.post(
            url,
            content=prepared_request["payload"],
            headers=headers
        )
        
        return response
    
    async def _process_secure_response(
        self,
        request_id: str,
        response: httpx.Response,
        security_level: TransmissionSecurityLevel,
        start_time: datetime
    ) -> SecureTransmissionResponse:
        """Process and validate secure response."""
        transmission_time = (datetime.now() - start_time).total_seconds() * 1000
        audit_trail = []
        
        # Validate response security
        security_validated = self._validate_response_security(response, security_level)
        audit_trail.append(f"Security validation: {'passed' if security_validated else 'failed'}")
        
        # Process response content
        decryption_successful = True
        response_data = None
        error_message = None
        
        try:
            if response.status_code == 200:
                response_content = response.text
                
                # Check if response is encrypted
                if security_level == TransmissionSecurityLevel.MAXIMUM:
                    try:
                        encrypted_response = json.loads(response_content)
                        if "encrypted_data" in encrypted_response:
                            # Decrypt response
                            encrypted_payload = EncryptedPayload(
                                encrypted_data=encrypted_response["encrypted_data"],
                                encryption_method=encrypted_response["encryption_method"],
                                key_id=encrypted_response["key_id"],
                                iv=encrypted_response["iv"],
                                auth_tag=encrypted_response.get("auth_tag")
                            )
                            response_content = self.payload_encryptor.decrypt_payload(encrypted_payload)
                            audit_trail.append("Response decryption: successful")
                        else:
                            audit_trail.append("Response decryption: not required")
                    except Exception as e:
                        decryption_successful = False
                        error_message = f"Response decryption failed: {str(e)}"
                        audit_trail.append(f"Response decryption: failed - {str(e)}")
                
                # Parse final response
                try:
                    response_data = json.loads(response_content)
                except json.JSONDecodeError:
                    response_data = response_content
                    
            else:
                error_message = f"HTTP {response.status_code}: {response.text}"
                audit_trail.append(f"HTTP error: {error_message}")
                
        except Exception as e:
            decryption_successful = False
            error_message = f"Response processing failed: {str(e)}"
            audit_trail.append(f"Response processing: failed - {str(e)}")
        
        # Create HuggingFace response
        hf_response = HuggingFaceResponse(
            model_id="secure_transmission",
            response_data=response_data,
            processing_time_ms=transmission_time,
            success=response.status_code == 200 and decryption_successful,
            error_message=error_message
        )
        
        return SecureTransmissionResponse(
            request_id=request_id,
            original_response=hf_response,
            security_validated=security_validated,
            decryption_successful=decryption_successful,
            transmission_time_ms=transmission_time,
            security_level_used=security_level,
            audit_trail=audit_trail
        )
    
    def _validate_response_security(
        self,
        response: httpx.Response,
        security_level: TransmissionSecurityLevel
    ) -> bool:
        """Validate response security headers and properties."""
        # Check TLS
        if not response.url.scheme == "https":
            return False
        
        # Check security headers for enhanced/maximum security
        if security_level in [TransmissionSecurityLevel.ENHANCED, TransmissionSecurityLevel.MAXIMUM]:
            required_headers = ["X-Request-ID", "X-Timestamp"]
            for header in required_headers:
                if header not in response.headers:
                    return False
        
        # Additional validation can be added here
        return True
    
    def _log_transmission_event(
        self,
        event_type: str,
        secure_request: SecureTransmissionRequest,
        details: Dict[str, Any]
    ):
        """Log transmission event for audit purposes."""
        self.audit_logger.log_event(
            event_type=AuditEventType.LLM_EXTERNAL_CALL,
            action=event_type,
            outcome="success" if "error" not in details else "failure",
            request_id=secure_request.request_id,
            security_level=SecurityLevel.HIGH if secure_request.phi_involved else SecurityLevel.MEDIUM,
            phi_involved=secure_request.phi_involved,
            compliance_flags=["HIPAA", "TLS", "Encryption"] if secure_request.phi_involved else ["TLS"],
            details={
                "security_level": secure_request.security_level.value,
                "transmission_method": secure_request.transmission_method.value,
                "encrypted": secure_request.encrypted_payload is not None,
                "signed": secure_request.security_headers is not None,
                **details
            }
        )
    
    def get_security_status(self) -> Dict[str, Any]:
        """Get current security configuration status."""
        return {
            "ssl_context_configured": self._ssl_context is not None,
            "client_certificates_loaded": bool(os.getenv("LLM_CLIENT_CERT_PATH")),
            "signing_key_configured": True,  # Always true as we generate if missing
            "supported_security_levels": [level.value for level in TransmissionSecurityLevel],
            "supported_transmission_methods": [method.value for method in TransmissionMethod],
            "tls_version": "TLSv1.2+",
            "encryption_algorithm": "AES-256-GCM",
            "signature_algorithm": "HMAC-SHA256"
        }


# Global service instance
secure_llm_transmission_service = SecureLLMTransmissionService()