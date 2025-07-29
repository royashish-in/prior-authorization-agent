"""
Cache warming service for the Prior Authorization Agent.

This module provides cache warming functionality for frequently accessed data
including policies, medical codes, and decision patterns.
"""

import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Set
from collections import defaultdict

from src.services.cache import cache_manager, CacheKey, CacheTTL
from src.services.policy_cache import policy_cache_service
from src.services.medical_code_cache import medical_code_cache_service, MedicalCodeType
from src.services.decision_cache import decision_cache_service

logger = logging.getLogger(__name__)


class CacheWarmingService:
    """
    Service for warming cache with frequently accessed data.
    
    Provides intelligent cache warming based on usage patterns,
    time-based warming schedules, and predictive pre-loading.
    """
    
    def __init__(self):
        self.cache = cache_manager
        self.policy_cache = policy_cache_service
        self.medical_code_cache = medical_code_cache_service
        self.decision_cache = decision_cache_service
    
    async def warm_frequently_accessed_data(self) -> Dict[str, Any]:
        """
        Warm cache with frequently accessed data across all categories.
        
        Returns:
            Dictionary with warming results for each category
        """
        logger.info("Starting cache warming for frequently accessed data")
        
        results = {
            'policies': {},
            'medical_codes': {},
            'validation_patterns': {},
            'started_at': datetime.now(timezone.utc).isoformat(),
            'total_warmed': 0
        }
        
        try:
            # Warm frequently accessed policies
            frequent_policies = await self._get_frequent_policy_ids()
            if frequent_policies:
                results['policies'] = await self.policy_cache.warm_frequently_accessed_policies(
                    frequent_policies
                )
            
            # Warm frequently used medical codes
            frequent_codes = await self._get_frequent_medical_codes()
            if frequent_codes:
                results['medical_codes'] = await self.medical_code_cache.warm_frequently_used_codes(
                    frequent_codes
                )
            
            # Warm common validation patterns
            validation_patterns = await self._warm_validation_patterns()
            results['validation_patterns'] = validation_patterns
            
            # Calculate total warmed items
            results['total_warmed'] = (
                sum(1 for success in results['policies'].values() if success) +
                sum(1 for success in results['medical_codes'].values() if success) +
                results['validation_patterns'].get('warmed_count', 0)
            )
            
            results['completed_at'] = datetime.now(timezone.utc).isoformat()
            logger.info(f"Cache warming completed. Total items warmed: {results['total_warmed']}")
            
        except Exception as e:
            logger.error(f"Cache warming failed: {e}")
            results['error'] = str(e)
        
        return results
    
    async def warm_payer_specific_data(self, payer_id: str) -> Dict[str, Any]:
        """
        Warm cache with payer-specific frequently accessed data.
        
        Args:
            payer_id: Payer identifier
            
        Returns:
            Dictionary with warming results
        """
        logger.info(f"Starting payer-specific cache warming for {payer_id}")
        
        results = {
            'payer_id': payer_id,
            'policies_warmed': 0,
            'codes_warmed': 0,
            'started_at': datetime.now(timezone.utc).isoformat()
        }
        
        try:
            # Get payer-specific frequent data
            payer_policies = await self._get_payer_frequent_policies(payer_id)
            payer_codes = await self._get_payer_frequent_codes(payer_id)
            
            # Warm payer policies
            if payer_policies:
                policy_results = await self.policy_cache.warm_frequently_accessed_policies(
                    payer_policies
                )
                results['policies_warmed'] = sum(
                    1 for success in policy_results.values() if success
                )
            
            # Warm payer-specific medical codes
            if payer_codes:
                code_results = await self.medical_code_cache.warm_frequently_used_codes(
                    payer_codes
                )
                results['codes_warmed'] = sum(
                    1 for success in code_results.values() if success
                )
            
            results['completed_at'] = datetime.now(timezone.utc).isoformat()
            logger.info(f"Payer {payer_id} cache warming completed")
            
        except Exception as e:
            logger.error(f"Payer-specific cache warming failed for {payer_id}: {e}")
            results['error'] = str(e)
        
        return results
    
    async def warm_time_based_data(self) -> Dict[str, Any]:
        """
        Warm cache based on time patterns (e.g., morning rush, end of day).
        
        Returns:
            Dictionary with warming results
        """
        current_hour = datetime.now(timezone.utc).hour
        
        logger.info(f"Starting time-based cache warming for hour {current_hour}")
        
        results = {
            'hour': current_hour,
            'warming_strategy': self._get_time_based_strategy(current_hour),
            'items_warmed': 0,
            'started_at': datetime.now(timezone.utc).isoformat()
        }
        
        try:
            strategy = results['warming_strategy']
            
            if strategy == 'morning_rush':
                # Warm common morning procedures
                morning_codes = await self._get_morning_rush_codes()
                if morning_codes:
                    code_results = await self.medical_code_cache.warm_frequently_used_codes(
                        morning_codes
                    )
                    results['items_warmed'] = sum(
                        1 for success in code_results.values() if success
                    )
            
            elif strategy == 'end_of_day':
                # Warm pending decision data
                pending_warming = await self._warm_pending_decisions()
                results['items_warmed'] = pending_warming.get('warmed_count', 0)
            
            elif strategy == 'weekend_prep':
                # Warm emergency/urgent care data
                urgent_data = await self._warm_urgent_care_data()
                results['items_warmed'] = urgent_data.get('warmed_count', 0)
            
            results['completed_at'] = datetime.now(timezone.utc).isoformat()
            logger.info(f"Time-based cache warming completed for {strategy}")
            
        except Exception as e:
            logger.error(f"Time-based cache warming failed: {e}")
            results['error'] = str(e)
        
        return results
    
    async def warm_predictive_data(self, request_patterns: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Warm cache based on predictive patterns from recent requests.
        
        Args:
            request_patterns: List of recent request patterns for prediction
            
        Returns:
            Dictionary with warming results
        """
        logger.info("Starting predictive cache warming")
        
        results = {
            'patterns_analyzed': len(request_patterns),
            'predictions_made': 0,
            'items_warmed': 0,
            'started_at': datetime.now(timezone.utc).isoformat()
        }
        
        try:
            # Analyze patterns to predict likely future requests
            predictions = await self._analyze_request_patterns(request_patterns)
            results['predictions_made'] = len(predictions)
            
            # Warm cache based on predictions
            warmed_count = 0
            for prediction in predictions:
                if prediction['type'] == 'policy':
                    policy_results = await self.policy_cache.warm_frequently_accessed_policies(
                        [prediction['policy_id']]
                    )
                    warmed_count += sum(1 for success in policy_results.values() if success)
                
                elif prediction['type'] == 'medical_code':
                    code_results = await self.medical_code_cache.warm_frequently_used_codes(
                        [(prediction['code'], prediction['code_type'])]
                    )
                    warmed_count += sum(1 for success in code_results.values() if success)
            
            results['items_warmed'] = warmed_count
            results['completed_at'] = datetime.now(timezone.utc).isoformat()
            logger.info(f"Predictive cache warming completed. Items warmed: {warmed_count}")
            
        except Exception as e:
            logger.error(f"Predictive cache warming failed: {e}")
            results['error'] = str(e)
        
        return results
    
    async def get_warming_recommendations(self) -> Dict[str, Any]:
        """
        Get recommendations for cache warming based on current cache state.
        
        Returns:
            Dictionary with warming recommendations
        """
        recommendations = {
            'policy_recommendations': [],
            'code_recommendations': [],
            'general_recommendations': [],
            'priority_level': 'normal'
        }
        
        try:
            # Analyze current cache statistics
            policy_stats = await self.policy_cache.get_cache_stats()
            code_stats = await self.medical_code_cache.get_cache_stats()
            decision_stats = await self.decision_cache.get_cache_stats()
            
            # Generate recommendations based on stats
            if policy_stats['active_policies'] < 10:
                recommendations['policy_recommendations'].append(
                    "Low number of active policies cached. Consider warming frequently used policies."
                )
                recommendations['priority_level'] = 'high'
            
            if code_stats['valid_codes'] < 50:
                recommendations['code_recommendations'].append(
                    "Low number of medical codes cached. Consider warming common ICD-10 and CPT codes."
                )
            
            if decision_stats['pending_decisions'] > 100:
                recommendations['general_recommendations'].append(
                    "High number of pending decisions. Consider warming validation patterns."
                )
                recommendations['priority_level'] = 'high'
            
            # Add time-based recommendations
            current_hour = datetime.now(timezone.utc).hour
            if 7 <= current_hour <= 9:
                recommendations['general_recommendations'].append(
                    "Morning rush period detected. Consider warming common morning procedures."
                )
            elif 16 <= current_hour <= 18:
                recommendations['general_recommendations'].append(
                    "End of day period detected. Consider warming pending decision data."
                )
        
        except Exception as e:
            logger.error(f"Failed to generate warming recommendations: {e}")
            recommendations['error'] = str(e)
        
        return recommendations
    
    async def _get_frequent_policy_ids(self) -> List[str]:
        """Get list of frequently accessed policy IDs."""
        # In a real implementation, this would query usage statistics
        # For now, return a placeholder list
        return [
            "policy_mri_brain_001",
            "policy_ct_chest_002", 
            "policy_xray_spine_003",
            "policy_ultrasound_abd_004",
            "policy_mri_knee_005"
        ]
    
    async def _get_frequent_medical_codes(self) -> List[tuple]:
        """Get list of frequently used medical codes."""
        # In a real implementation, this would query usage statistics
        return [
            ("70551", MedicalCodeType.CPT),  # MRI brain without contrast
            ("71020", MedicalCodeType.CPT),  # Chest X-ray
            ("72148", MedicalCodeType.CPT),  # MRI lumbar spine
            ("G0202", MedicalCodeType.HCPCS), # Screening mammography
            ("M79.3", MedicalCodeType.ICD10),  # Panniculitis
            ("S72.001A", MedicalCodeType.ICD10)  # Fracture of femur
        ]
    
    async def _get_payer_frequent_policies(self, payer_id: str) -> List[str]:
        """Get frequently accessed policies for a specific payer."""
        # In a real implementation, this would query payer-specific usage
        return [f"policy_{payer_id}_001", f"policy_{payer_id}_002"]
    
    async def _get_payer_frequent_codes(self, payer_id: str) -> List[tuple]:
        """Get frequently used codes for a specific payer."""
        # In a real implementation, this would query payer-specific code usage
        return [
            ("70551", MedicalCodeType.CPT),
            ("M79.3", MedicalCodeType.ICD10)
        ]
    
    async def _warm_validation_patterns(self) -> Dict[str, Any]:
        """Warm common validation patterns."""
        # Placeholder implementation
        return {'warmed_count': 5, 'patterns': ['common_mri', 'common_ct']}
    
    async def _get_morning_rush_codes(self) -> List[tuple]:
        """Get medical codes commonly used during morning rush."""
        return [
            ("70551", MedicalCodeType.CPT),  # MRI brain
            ("71020", MedicalCodeType.CPT),  # Chest X-ray
            ("M79.3", MedicalCodeType.ICD10)  # Common diagnosis
        ]
    
    async def _warm_pending_decisions(self) -> Dict[str, Any]:
        """Warm data related to pending decisions."""
        return {'warmed_count': 10}
    
    async def _warm_urgent_care_data(self) -> Dict[str, Any]:
        """Warm urgent care related data."""
        return {'warmed_count': 8}
    
    async def _analyze_request_patterns(
        self, 
        patterns: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Analyze request patterns to make predictions."""
        predictions = []
        
        # Simple pattern analysis - in production this would be more sophisticated
        code_frequency = defaultdict(int)
        
        for pattern in patterns:
            for code in pattern.get('procedure_codes', []):
                code_frequency[code] += 1
        
        # Predict top codes will be requested again
        for code, frequency in sorted(code_frequency.items(), key=lambda x: x[1], reverse=True)[:5]:
            predictions.append({
                'type': 'medical_code',
                'code': code,
                'code_type': MedicalCodeType.CPT,  # Assume CPT for simplicity
                'confidence': min(frequency / len(patterns), 1.0)
            })
        
        return predictions
    
    def _get_time_based_strategy(self, hour: int) -> str:
        """Get warming strategy based on time of day."""
        if 7 <= hour <= 9:
            return 'morning_rush'
        elif 16 <= hour <= 18:
            return 'end_of_day'
        elif hour >= 22 or hour <= 6:
            return 'weekend_prep'
        else:
            return 'normal'


# Global cache warming service instance
cache_warming_service = CacheWarmingService()