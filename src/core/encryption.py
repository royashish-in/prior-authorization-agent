"""
PHI encryption and decryption utilities using AES-256.

This module provides secure encryption/decryption for Protected Health Information (PHI)
in compliance with HIPAA requirements.
"""

import base64
import os
from typing import Optional, Union
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class PHIEncryption:
    """
    PHI encryption utility using AES-256 encryption.
    
    Provides methods to encrypt and decrypt sensitive healthcare data
    with proper key management and security practices.
    """
    
    def __init__(self, master_key: Optional[str] = None):
        """
        Initialize encryption utility.
        
        Args:
            master_key: Master encryption key. If None, uses environment variable.
        """
        self._master_key = master_key or os.getenv('PHI_MASTER_KEY')
        if not self._master_key:
            raise ValueError("PHI_MASTER_KEY environment variable must be set")
        
        # Derive encryption key from master key
        self._fernet = self._create_fernet_key(self._master_key)
    
    def _create_fernet_key(self, master_key: str) -> Fernet:
        """
        Create Fernet encryption key from master key.
        
        Args:
            master_key: Master key string
            
        Returns:
            Fernet encryption instance
        """
        # Use a fixed salt for key derivation (in production, use per-record salts)
        salt = b'phi_encryption_salt_2024'
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        
        key = base64.urlsafe_b64encode(kdf.derive(master_key.encode()))
        return Fernet(key)
    
    def encrypt(self, plaintext: Union[str, bytes]) -> str:
        """
        Encrypt plaintext data.
        
        Args:
            plaintext: Data to encrypt (string or bytes)
            
        Returns:
            Base64-encoded encrypted data
            
        Raises:
            ValueError: If plaintext is empty or None
            Exception: If encryption fails
        """
        if not plaintext:
            raise ValueError("Cannot encrypt empty or None data")
        
        try:
            # Convert string to bytes if necessary
            if isinstance(plaintext, str):
                plaintext_bytes = plaintext.encode('utf-8')
            else:
                plaintext_bytes = plaintext
            
            # Encrypt the data
            encrypted_data = self._fernet.encrypt(plaintext_bytes)
            
            # Return base64-encoded string for storage
            return base64.urlsafe_b64encode(encrypted_data).decode('utf-8')
            
        except Exception as e:
            raise Exception(f"Encryption failed: {str(e)}")
    
    def decrypt(self, encrypted_data: str) -> str:
        """
        Decrypt encrypted data.
        
        Args:
            encrypted_data: Base64-encoded encrypted data
            
        Returns:
            Decrypted plaintext string
            
        Raises:
            ValueError: If encrypted_data is empty or None
            Exception: If decryption fails
        """
        if not encrypted_data:
            raise ValueError("Cannot decrypt empty or None data")
        
        try:
            # Decode from base64
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode('utf-8'))
            
            # Decrypt the data
            decrypted_bytes = self._fernet.decrypt(encrypted_bytes)
            
            # Return as string
            return decrypted_bytes.decode('utf-8')
            
        except Exception as e:
            raise Exception(f"Decryption failed: {str(e)}")
    
    def encrypt_patient_id(self, patient_id: str) -> str:
        """
        Encrypt patient identifier with specific prefix.
        
        Args:
            patient_id: Plain patient ID
            
        Returns:
            Encrypted patient ID with 'enc_pat_' prefix
        """
        if not patient_id:
            raise ValueError("Patient ID cannot be empty")
        
        encrypted = self.encrypt(patient_id)
        return f"enc_pat_{encrypted}"
    
    def decrypt_patient_id(self, encrypted_patient_id: str) -> str:
        """
        Decrypt patient identifier.
        
        Args:
            encrypted_patient_id: Encrypted patient ID with prefix
            
        Returns:
            Plain patient ID
        """
        if not encrypted_patient_id or not encrypted_patient_id.startswith('enc_pat_'):
            raise ValueError("Invalid encrypted patient ID format")
        
        encrypted_data = encrypted_patient_id[8:]  # Remove 'enc_pat_' prefix
        return self.decrypt(encrypted_data)
    
    def encrypt_insurance_id(self, insurance_id: str) -> str:
        """
        Encrypt insurance identifier with specific prefix.
        
        Args:
            insurance_id: Plain insurance ID
            
        Returns:
            Encrypted insurance ID with 'enc_ins_' prefix
        """
        if not insurance_id:
            raise ValueError("Insurance ID cannot be empty")
        
        encrypted = self.encrypt(insurance_id)
        return f"enc_ins_{encrypted}"
    
    def decrypt_insurance_id(self, encrypted_insurance_id: str) -> str:
        """
        Decrypt insurance identifier.
        
        Args:
            encrypted_insurance_id: Encrypted insurance ID with prefix
            
        Returns:
            Plain insurance ID
        """
        if not encrypted_insurance_id or not encrypted_insurance_id.startswith('enc_ins_'):
            raise ValueError("Invalid encrypted insurance ID format")
        
        encrypted_data = encrypted_insurance_id[8:]  # Remove 'enc_ins_' prefix
        return self.decrypt(encrypted_data)
    
    def encrypt_member_id(self, member_id: str) -> str:
        """
        Encrypt member identifier with specific prefix.
        
        Args:
            member_id: Plain member ID
            
        Returns:
            Encrypted member ID with 'enc_mem_' prefix
        """
        if not member_id:
            raise ValueError("Member ID cannot be empty")
        
        encrypted = self.encrypt(member_id)
        return f"enc_mem_{encrypted}"
    
    def decrypt_member_id(self, encrypted_member_id: str) -> str:
        """
        Decrypt member identifier.
        
        Args:
            encrypted_member_id: Encrypted member ID with prefix
            
        Returns:
            Plain member ID
        """
        if not encrypted_member_id or not encrypted_member_id.startswith('enc_mem_'):
            raise ValueError("Invalid encrypted member ID format")
        
        encrypted_data = encrypted_member_id[8:]  # Remove 'enc_mem_' prefix
        return self.decrypt(encrypted_data)
    
    def encrypt_clinical_notes(self, clinical_notes: str) -> str:
        """
        Encrypt clinical notes.
        
        Args:
            clinical_notes: Plain clinical notes
            
        Returns:
            Encrypted clinical notes
        """
        if not clinical_notes:
            return ""
        
        return self.encrypt(clinical_notes)
    
    def decrypt_clinical_notes(self, encrypted_notes: str) -> str:
        """
        Decrypt clinical notes.
        
        Args:
            encrypted_notes: Encrypted clinical notes
            
        Returns:
            Plain clinical notes
        """
        if not encrypted_notes:
            return ""
        
        return self.decrypt(encrypted_notes)


# Global encryption instance (initialized when needed)
_encryption_instance: Optional[PHIEncryption] = None


def get_phi_encryption() -> PHIEncryption:
    """
    Get global PHI encryption instance.
    
    Returns:
        PHIEncryption instance
    """
    global _encryption_instance
    if _encryption_instance is None:
        _encryption_instance = PHIEncryption()
    return _encryption_instance


def encrypt_phi_field(data: str, field_type: str = "generic") -> str:
    """
    Convenience function to encrypt PHI field.
    
    Args:
        data: Data to encrypt
        field_type: Type of field (patient_id, insurance_id, member_id, clinical_notes)
        
    Returns:
        Encrypted data with appropriate prefix
    """
    encryption = get_phi_encryption()
    
    if field_type == "patient_id":
        return encryption.encrypt_patient_id(data)
    elif field_type == "insurance_id":
        return encryption.encrypt_insurance_id(data)
    elif field_type == "member_id":
        return encryption.encrypt_member_id(data)
    elif field_type == "clinical_notes":
        return encryption.encrypt_clinical_notes(data)
    else:
        return encryption.encrypt(data)


def decrypt_phi_field(encrypted_data: str, field_type: str = "generic") -> str:
    """
    Convenience function to decrypt PHI field.
    
    Args:
        encrypted_data: Encrypted data
        field_type: Type of field (patient_id, insurance_id, member_id, clinical_notes)
        
    Returns:
        Decrypted data
    """
    encryption = get_phi_encryption()
    
    if field_type == "patient_id":
        return encryption.decrypt_patient_id(encrypted_data)
    elif field_type == "insurance_id":
        return encryption.decrypt_insurance_id(encrypted_data)
    elif field_type == "member_id":
        return encryption.decrypt_member_id(encrypted_data)
    elif field_type == "clinical_notes":
        return encryption.decrypt_clinical_notes(encrypted_data)
    else:
        return encryption.decrypt(encrypted_data)


def encrypt_data(data: str, key: bytes) -> str:
    """
    Encrypt data using provided key for audit logging.
    
    Args:
        data: Data to encrypt
        key: Encryption key (32 bytes for AES-256)
        
    Returns:
        Encrypted data as base64 string
    """
    from cryptography.fernet import Fernet
    import base64
    
    # Create Fernet key from provided bytes
    fernet_key = base64.urlsafe_b64encode(key)
    fernet = Fernet(fernet_key)
    
    # Encrypt the data
    encrypted_bytes = fernet.encrypt(data.encode('utf-8'))
    
    # Return as base64 string
    return base64.urlsafe_b64encode(encrypted_bytes).decode('utf-8')


def decrypt_data(encrypted_data: str, key: bytes) -> str:
    """
    Decrypt data using provided key for audit logging.
    
    Args:
        encrypted_data: Base64 encrypted data
        key: Decryption key (32 bytes for AES-256)
        
    Returns:
        Decrypted data as string
    """
    from cryptography.fernet import Fernet
    import base64
    
    # Create Fernet key from provided bytes
    fernet_key = base64.urlsafe_b64encode(key)
    fernet = Fernet(fernet_key)
    
    # Decode from base64
    encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode('utf-8'))
    
    # Decrypt the data
    decrypted_bytes = fernet.decrypt(encrypted_bytes)
    
    # Return as string
    return decrypted_bytes.decode('utf-8')