"""
Unit tests for PHI encryption utilities.
"""

import pytest
import os
from unittest.mock import patch

from src.core.encryption import (
    PHIEncryption,
    get_phi_encryption,
    encrypt_phi_field,
    decrypt_phi_field
)


class TestPHIEncryption:
    """Test PHI encryption functionality."""
    
    @pytest.fixture
    def encryption(self):
        """Create encryption instance for testing."""
        test_key = "test_master_key_for_phi_encryption_2024"
        return PHIEncryption(master_key=test_key)
    
    def test_basic_encryption_decryption(self, encryption):
        """Test basic encryption and decryption."""
        plaintext = "sensitive_patient_data"
        
        # Encrypt the data
        encrypted = encryption.encrypt(plaintext)
        assert encrypted != plaintext
        assert len(encrypted) > len(plaintext)
        
        # Decrypt the data
        decrypted = encryption.decrypt(encrypted)
        assert decrypted == plaintext
    
    def test_encrypt_empty_data(self, encryption):
        """Test encryption of empty data."""
        with pytest.raises(ValueError, match="Cannot encrypt empty or None data"):
            encryption.encrypt("")
        
        with pytest.raises(ValueError, match="Cannot encrypt empty or None data"):
            encryption.encrypt(None)
    
    def test_decrypt_empty_data(self, encryption):
        """Test decryption of empty data."""
        with pytest.raises(ValueError, match="Cannot decrypt empty or None data"):
            encryption.decrypt("")
        
        with pytest.raises(ValueError, match="Cannot decrypt empty or None data"):
            encryption.decrypt(None)
    
    def test_encrypt_bytes(self, encryption):
        """Test encryption of byte data."""
        plaintext_bytes = b"sensitive_patient_data"
        
        encrypted = encryption.encrypt(plaintext_bytes)
        decrypted = encryption.decrypt(encrypted)
        
        assert decrypted == plaintext_bytes.decode('utf-8')
    
    def test_patient_id_encryption(self, encryption):
        """Test patient ID encryption with prefix."""
        patient_id = "patient_12345"
        
        encrypted = encryption.encrypt_patient_id(patient_id)
        assert encrypted.startswith("enc_pat_")
        
        decrypted = encryption.decrypt_patient_id(encrypted)
        assert decrypted == patient_id
    
    def test_insurance_id_encryption(self, encryption):
        """Test insurance ID encryption with prefix."""
        insurance_id = "insurance_67890"
        
        encrypted = encryption.encrypt_insurance_id(insurance_id)
        assert encrypted.startswith("enc_ins_")
        
        decrypted = encryption.decrypt_insurance_id(encrypted)
        assert decrypted == insurance_id
    
    def test_member_id_encryption(self, encryption):
        """Test member ID encryption with prefix."""
        member_id = "member_abcdef"
        
        encrypted = encryption.encrypt_member_id(member_id)
        assert encrypted.startswith("enc_mem_")
        
        decrypted = encryption.decrypt_member_id(encrypted)
        assert decrypted == member_id
    
    def test_clinical_notes_encryption(self, encryption):
        """Test clinical notes encryption."""
        notes = "Patient reports severe pain in right shoulder for 6 weeks. Conservative treatment has failed."
        
        encrypted = encryption.encrypt_clinical_notes(notes)
        assert encrypted != notes
        
        decrypted = encryption.decrypt_clinical_notes(encrypted)
        assert decrypted == notes
    
    def test_empty_clinical_notes(self, encryption):
        """Test encryption of empty clinical notes."""
        encrypted = encryption.encrypt_clinical_notes("")
        assert encrypted == ""
        
        decrypted = encryption.decrypt_clinical_notes("")
        assert decrypted == ""
    
    def test_invalid_encrypted_patient_id(self, encryption):
        """Test decryption of invalid patient ID format."""
        with pytest.raises(ValueError, match="Invalid encrypted patient ID format"):
            encryption.decrypt_patient_id("invalid_format")
        
        with pytest.raises(ValueError, match="Invalid encrypted patient ID format"):
            encryption.decrypt_patient_id("")
    
    def test_invalid_encrypted_insurance_id(self, encryption):
        """Test decryption of invalid insurance ID format."""
        with pytest.raises(ValueError, match="Invalid encrypted insurance ID format"):
            encryption.decrypt_insurance_id("invalid_format")
    
    def test_invalid_encrypted_member_id(self, encryption):
        """Test decryption of invalid member ID format."""
        with pytest.raises(ValueError, match="Invalid encrypted member ID format"):
            encryption.decrypt_member_id("invalid_format")
    
    def test_empty_phi_fields(self, encryption):
        """Test encryption of empty PHI fields."""
        with pytest.raises(ValueError, match="Patient ID cannot be empty"):
            encryption.encrypt_patient_id("")
        
        with pytest.raises(ValueError, match="Insurance ID cannot be empty"):
            encryption.encrypt_insurance_id("")
        
        with pytest.raises(ValueError, match="Member ID cannot be empty"):
            encryption.encrypt_member_id("")
    
    def test_encryption_consistency(self, encryption):
        """Test that encryption produces different results each time."""
        plaintext = "consistent_test_data"
        
        encrypted1 = encryption.encrypt(plaintext)
        encrypted2 = encryption.encrypt(plaintext)
        
        # Encrypted values should be different (due to random IV)
        assert encrypted1 != encrypted2
        
        # But both should decrypt to the same plaintext
        assert encryption.decrypt(encrypted1) == plaintext
        assert encryption.decrypt(encrypted2) == plaintext
    
    def test_invalid_decryption_data(self, encryption):
        """Test decryption of invalid data."""
        with pytest.raises(Exception, match="Decryption failed"):
            encryption.decrypt("invalid_encrypted_data")
    
    def test_missing_master_key(self):
        """Test initialization without master key."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="PHI_MASTER_KEY environment variable must be set"):
                PHIEncryption()


class TestGlobalEncryptionFunctions:
    """Test global encryption convenience functions."""
    
    @patch.dict(os.environ, {'PHI_MASTER_KEY': 'test_master_key_for_global_functions'})
    def test_get_phi_encryption(self):
        """Test global encryption instance."""
        encryption1 = get_phi_encryption()
        encryption2 = get_phi_encryption()
        
        # Should return the same instance
        assert encryption1 is encryption2
    
    @patch.dict(os.environ, {'PHI_MASTER_KEY': 'test_master_key_for_convenience_functions'})
    def test_encrypt_decrypt_phi_field_patient_id(self):
        """Test convenience functions for patient ID."""
        patient_id = "patient_12345"
        
        encrypted = encrypt_phi_field(patient_id, "patient_id")
        assert encrypted.startswith("enc_pat_")
        
        decrypted = decrypt_phi_field(encrypted, "patient_id")
        assert decrypted == patient_id
    
    @patch.dict(os.environ, {'PHI_MASTER_KEY': 'test_master_key_for_convenience_functions'})
    def test_encrypt_decrypt_phi_field_insurance_id(self):
        """Test convenience functions for insurance ID."""
        insurance_id = "insurance_67890"
        
        encrypted = encrypt_phi_field(insurance_id, "insurance_id")
        assert encrypted.startswith("enc_ins_")
        
        decrypted = decrypt_phi_field(encrypted, "insurance_id")
        assert decrypted == insurance_id
    
    @patch.dict(os.environ, {'PHI_MASTER_KEY': 'test_master_key_for_convenience_functions'})
    def test_encrypt_decrypt_phi_field_member_id(self):
        """Test convenience functions for member ID."""
        member_id = "member_abcdef"
        
        encrypted = encrypt_phi_field(member_id, "member_id")
        assert encrypted.startswith("enc_mem_")
        
        decrypted = decrypt_phi_field(encrypted, "member_id")
        assert decrypted == member_id
    
    @patch.dict(os.environ, {'PHI_MASTER_KEY': 'test_master_key_for_convenience_functions'})
    def test_encrypt_decrypt_phi_field_clinical_notes(self):
        """Test convenience functions for clinical notes."""
        notes = "Patient has chronic pain condition requiring imaging."
        
        encrypted = encrypt_phi_field(notes, "clinical_notes")
        assert encrypted != notes
        
        decrypted = decrypt_phi_field(encrypted, "clinical_notes")
        assert decrypted == notes
    
    @patch.dict(os.environ, {'PHI_MASTER_KEY': 'test_master_key_for_convenience_functions'})
    def test_encrypt_decrypt_phi_field_generic(self):
        """Test convenience functions for generic data."""
        data = "generic_sensitive_data"
        
        encrypted = encrypt_phi_field(data, "generic")
        assert encrypted != data
        
        decrypted = decrypt_phi_field(encrypted, "generic")
        assert decrypted == data