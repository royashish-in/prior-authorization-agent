"""
Semantic Similarity Service for Medical Decision Caching

This service provides semantic similarity matching for medical authorization requests
to enable intelligent caching of similar scenarios and improve response times.
"""

import asyncio
import logging
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import pickle
import os

from ..models.authorization import AuthorizationRequest
from ..models.medical_codes import ICD10Code, CPTCode
from .cache import cache_manager, CacheKey, CacheTTL

logger = logging.getLogger(__name__)


@dataclass
class SimilarityFeatures:
    """Features extracted from authorization request for similarity matching."""
    diagnosis_codes: List[str] = field(default_factory=list)
    procedure_codes: List[str] = field(default_factory=list)
    clinical_text: str = ""
    patient_age_group: str = ""  # child, adult, elderly
    urgency_level: str = ""
    payer_type: str = ""
    specialty: str = ""
    
    def to_text(self) -> str:
        """Convert features to text representation for vectorization."""
        components = []
        
        # Add diagnosis codes
        if self.diagnosis_codes:
            components.append(f"diagnosis: {' '.join(self.diagnosis_codes)}")
        
        # Add procedure codes
        if self.procedure_codes:
            components.append(f"procedure: {' '.join(self.procedure_codes)}")
        
        # Add clinical text
        if self.clinical_text:
            components.append(f"clinical: {self.clinical_text}")
        
        # Add categorical features
        if self.patient_age_group:
            components.append(f"age_group: {self.patient_age_group}")
        
        if self.urgency_level:
            components.append(f"urgency: {self.urgency_level}")
        
        if self.payer_type:
            components.append(f"payer: {self.payer_type}")
        
        if self.specialty:
            components.append(f"specialty: {self.specialty}")
        
        return " ".join(components)


@dataclass
class SimilarityMatch:
    """Represents a similarity match result."""
    request_hash: str
    similarity_score: float
    cached_decision: Optional[Dict[str, Any]] = None
    match_features: Optional[SimilarityFeatures] = None
    cache_key: Optional[str] = None


class SemanticSimilarityService:
    """
    Service for semantic similarity matching of medical authorization requests.
    
    Uses TF-IDF vectorization and cosine similarity to find similar requests
    for intelligent caching and decision reuse.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.cache = cache_manager
        
        # Similarity matching parameters
        self.similarity_threshold = 0.85  # Minimum similarity for cache hit
        self.max_cached_vectors = 10000   # Maximum number of vectors to keep in memory
        self.vector_cache_ttl = 3600 * 24  # 24 hours
        
        # TF-IDF vectorizer for text similarity
        self.vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words='english',
            ngram_range=(1, 2),
            min_df=1,
            max_df=0.95
        )
        
        # In-memory cache for request vectors
        self._request_vectors: Dict[str, np.ndarray] = {}
        self._request_features: Dict[str, SimilarityFeatures] = {}
        self._vectorizer_fitted = False
        self._vector_cache_file = "similarity_vectors.pkl"
        
    async def initialize(self):
        """Initialize the semantic similarity service."""
        self.logger.info("Initializing Semantic Similarity Service")
        
        # Load cached vectors if available
        await self._load_vector_cache()
        
        self.logger.info("Semantic Similarity Service initialized")
    
    async def find_similar_requests(
        self,
        request: AuthorizationRequest,
        min_similarity: Optional[float] = None
    ) -> List[SimilarityMatch]:
        """
        Find similar authorization requests for cache lookup.
        
        Args:
            request: Authorization request to find matches for
            min_similarity: Minimum similarity threshold (defaults to service threshold)
            
        Returns:
            List of similarity matches sorted by similarity score
        """
        if min_similarity is None:
            min_similarity = self.similarity_threshold
        
        # Extract features from request
        features = self._extract_features(request)
        request_hash = self._hash_features(features)
        
        # Check if we already have this exact request
        if request_hash in self._request_vectors:
            self.logger.debug(f"Exact match found for request hash: {request_hash}")
            return []  # No need to find similar if exact match exists
        
        # Convert features to text for vectorization
        request_text = features.to_text()
        
        if not self._vectorizer_fitted or not self._request_vectors:
            self.logger.debug("No cached vectors available for similarity matching")
            return []
        
        try:
            # Vectorize the current request
            request_vector = self.vectorizer.transform([request_text])
            
            # Calculate similarities with all cached requests
            similarities = []
            for cached_hash, cached_vector in self._request_vectors.items():
                similarity = cosine_similarity(request_vector, cached_vector.reshape(1, -1))[0][0]
                
                if similarity >= min_similarity:
                    similarities.append((cached_hash, similarity))
            
            # Sort by similarity score (descending)
            similarities.sort(key=lambda x: x[1], reverse=True)
            
            # Build similarity matches
            matches = []
            for cached_hash, similarity_score in similarities[:10]:  # Top 10 matches
                # Try to get cached decision
                cached_decision = await self._get_cached_decision(cached_hash)
                
                match = SimilarityMatch(
                    request_hash=cached_hash,
                    similarity_score=similarity_score,
                    cached_decision=cached_decision,
                    match_features=self._request_features.get(cached_hash)
                )
                matches.append(match)
            
            self.logger.debug(f"Found {len(matches)} similar requests for {request_hash}")
            return matches
            
        except Exception as e:
            self.logger.error(f"Error finding similar requests: {str(e)}")
            return []
    
    async def cache_request_vector(
        self,
        request: AuthorizationRequest,
        decision: Dict[str, Any]
    ) -> str:
        """
        Cache the vector representation of a request for future similarity matching.
        
        Args:
            request: Authorization request to cache
            decision: Decision result to associate with the request
            
        Returns:
            Request hash for the cached vector
        """
        try:
            # Extract features
            features = self._extract_features(request)
            request_hash = self._hash_features(features)
            
            # Convert to text
            request_text = features.to_text()
            
            # Fit vectorizer if not already fitted
            if not self._vectorizer_fitted:
                await self._fit_vectorizer([request_text])
            
            # Vectorize the request
            request_vector = self.vectorizer.transform([request_text])
            
            # Store in memory cache
            self._request_vectors[request_hash] = request_vector.toarray()[0]
            self._request_features[request_hash] = features
            
            # Cache the decision with similarity metadata
            await self._cache_decision_with_similarity(request_hash, decision, features)
            
            # Periodically save vector cache
            if len(self._request_vectors) % 100 == 0:
                await self._save_vector_cache()
            
            self.logger.debug(f"Cached request vector: {request_hash}")
            return request_hash
            
        except Exception as e:
            self.logger.error(f"Error caching request vector: {str(e)}")
            return ""
    
    async def get_similarity_stats(self) -> Dict[str, Any]:
        """Get statistics about the similarity cache."""
        return {
            'total_cached_vectors': len(self._request_vectors),
            'vectorizer_fitted': self._vectorizer_fitted,
            'similarity_threshold': self.similarity_threshold,
            'max_cached_vectors': self.max_cached_vectors,
            'feature_dimensions': self.vectorizer.max_features if self._vectorizer_fitted else 0
        }
    
    async def clear_similarity_cache(self) -> bool:
        """Clear the similarity cache."""
        try:
            self._request_vectors.clear()
            self._request_features.clear()
            self._vectorizer_fitted = False
            
            # Remove cache file
            if os.path.exists(self._vector_cache_file):
                os.remove(self._vector_cache_file)
            
            self.logger.info("Similarity cache cleared")
            return True
            
        except Exception as e:
            self.logger.error(f"Error clearing similarity cache: {str(e)}")
            return False
    
    def _extract_features(self, request: AuthorizationRequest) -> SimilarityFeatures:
        """Extract similarity features from authorization request."""
        features = SimilarityFeatures()
        
        # Extract diagnosis codes
        if hasattr(request, 'diagnosis_codes') and request.diagnosis_codes:
            features.diagnosis_codes = [code.code if hasattr(code, 'code') else str(code) 
                                      for code in request.diagnosis_codes]
        
        # Extract procedure codes
        if hasattr(request, 'procedure_codes') and request.procedure_codes:
            features.procedure_codes = [code.code if hasattr(code, 'code') else str(code) 
                                      for code in request.procedure_codes]
        
        # Extract clinical text
        clinical_components = []
        if hasattr(request, 'clinical_notes') and request.clinical_notes:
            clinical_components.append(request.clinical_notes)
        if hasattr(request, 'provider_justification') and request.provider_justification:
            clinical_components.append(request.provider_justification)
        if hasattr(request, 'symptoms') and request.symptoms:
            clinical_components.append(' '.join(request.symptoms))
        
        features.clinical_text = ' '.join(clinical_components)
        
        # Extract patient age group
        if hasattr(request, 'patient_info') and request.patient_info:
            age = getattr(request.patient_info, 'age', None)
            if age is not None:
                if age < 18:
                    features.patient_age_group = "child"
                elif age < 65:
                    features.patient_age_group = "adult"
                else:
                    features.patient_age_group = "elderly"
        
        # Extract urgency level
        if hasattr(request, 'urgency_level'):
            features.urgency_level = str(request.urgency_level).lower()
        
        # Extract payer information
        if hasattr(request, 'payer_info') and request.payer_info:
            features.payer_type = getattr(request.payer_info, 'payer_type', '')
        
        # Extract provider specialty
        if hasattr(request, 'provider_info') and request.provider_info:
            features.specialty = getattr(request.provider_info, 'specialty', '')
        
        return features
    
    def _hash_features(self, features: SimilarityFeatures) -> str:
        """Create a hash of the features for caching."""
        # Create a deterministic representation
        feature_dict = {
            'diagnosis_codes': sorted(features.diagnosis_codes),
            'procedure_codes': sorted(features.procedure_codes),
            'clinical_text': features.clinical_text,
            'patient_age_group': features.patient_age_group,
            'urgency_level': features.urgency_level,
            'payer_type': features.payer_type,
            'specialty': features.specialty
        }
        
        feature_str = json.dumps(feature_dict, sort_keys=True)
        return hashlib.sha256(feature_str.encode()).hexdigest()
    
    async def _fit_vectorizer(self, texts: List[str]):
        """Fit the TF-IDF vectorizer with the provided texts."""
        try:
            # Add some medical domain-specific terms to ensure they're included
            medical_terms = [
                "diagnosis treatment procedure medical clinical patient",
                "surgery medication therapy examination imaging",
                "urgent routine emergency elective prior authorization"
            ]
            
            all_texts = texts + medical_terms
            self.vectorizer.fit(all_texts)
            self._vectorizer_fitted = True
            
            self.logger.debug(f"Vectorizer fitted with {len(all_texts)} texts")
            
        except Exception as e:
            self.logger.error(f"Error fitting vectorizer: {str(e)}")
    
    async def _get_cached_decision(self, request_hash: str) -> Optional[Dict[str, Any]]:
        """Get cached decision for a request hash."""
        cache_key = f"similarity:decision:{request_hash}"
        return await self.cache.get(cache_key)
    
    async def _cache_decision_with_similarity(
        self,
        request_hash: str,
        decision: Dict[str, Any],
        features: SimilarityFeatures
    ):
        """Cache decision with similarity metadata."""
        cache_key = f"similarity:decision:{request_hash}"
        
        enhanced_decision = {
            **decision,
            'similarity_metadata': {
                'request_hash': request_hash,
                'features': {
                    'diagnosis_codes': features.diagnosis_codes,
                    'procedure_codes': features.procedure_codes,
                    'patient_age_group': features.patient_age_group,
                    'urgency_level': features.urgency_level,
                    'payer_type': features.payer_type,
                    'specialty': features.specialty
                },
                'cached_at': datetime.now(timezone.utc).isoformat()
            }
        }
        
        await self.cache.set(cache_key, enhanced_decision, ttl=self.vector_cache_ttl)
    
    async def _save_vector_cache(self):
        """Save vector cache to disk."""
        try:
            cache_data = {
                'vectors': self._request_vectors,
                'features': {k: v.__dict__ for k, v in self._request_features.items()},
                'vectorizer': self.vectorizer if self._vectorizer_fitted else None,
                'fitted': self._vectorizer_fitted,
                'saved_at': datetime.now(timezone.utc).isoformat()
            }
            
            with open(self._vector_cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
            
            self.logger.debug(f"Vector cache saved to {self._vector_cache_file}")
            
        except Exception as e:
            self.logger.error(f"Error saving vector cache: {str(e)}")
    
    async def _load_vector_cache(self):
        """Load vector cache from disk."""
        try:
            if not os.path.exists(self._vector_cache_file):
                self.logger.debug("No vector cache file found")
                return
            
            with open(self._vector_cache_file, 'rb') as f:
                cache_data = pickle.load(f)
            
            self._request_vectors = cache_data.get('vectors', {})
            
            # Reconstruct features objects
            features_data = cache_data.get('features', {})
            self._request_features = {}
            for k, v in features_data.items():
                features = SimilarityFeatures()
                features.__dict__.update(v)
                self._request_features[k] = features
            
            # Restore vectorizer
            if cache_data.get('fitted', False) and cache_data.get('vectorizer'):
                self.vectorizer = cache_data['vectorizer']
                self._vectorizer_fitted = True
            
            self.logger.info(f"Loaded {len(self._request_vectors)} vectors from cache")
            
        except Exception as e:
            self.logger.error(f"Error loading vector cache: {str(e)}")
            # Clear corrupted cache
            self._request_vectors.clear()
            self._request_features.clear()
            self._vectorizer_fitted = False


# Global semantic similarity service instance
semantic_similarity_service = SemanticSimilarityService()