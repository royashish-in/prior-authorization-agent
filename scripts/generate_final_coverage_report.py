#!/usr/bin/env python3
"""
Final Coverage Improvement Report Generator

This script implements task 9.2: Generate final coverage improvement report
- Create comprehensive coverage improvement documentation
- Document which modules contributed most to coverage gains
- Generate before/after coverage comparison reports
- Provide recommendations for future coverage improvements
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.coverage_tracking.baseline_tracker import CoverageTracker, CoverageSnapshot


class FinalCoverageReportGenerator:
    """Generates comprehensive final coverage improvement reports."""
    
    def __init__(self):
        self.tracker = CoverageTracker()
        self.target_coverage = 30.0
        self.baseline_coverage = 16.09  # Updated baseline
        
        # Test file implementation status
        self.implemented_test_files = {
            "test_decision_engine_extended.py": {
                "expected_contribution": 150,
                "actual_file": "tests/test_decision_engine_extended.py",
                "status": "implemented",
                "priority": "high"
            },
            "test_llm_decisions_api_comprehensive.py": {
                "expected_contribution": 120,
                "actual_file": "tests/test_llm_decisions_api_comprehensive.py",
                "status": "implemented",
                "priority": "high"
            },
            "test_intake_api_extended.py": {
                "expected_contribution": 100,
                "actual_file": "tests/test_intake_api_extended.py",
                "status": "implemented",
                "priority": "high"
            },
            "test_validation_service_extended.py": {
                "expected_contribution": 80,
                "actual_file": "tests/test_validation_service_extended.py",
                "status": "implemented",
                "priority": "medium"
            },
            "test_tracking_service_extended.py": {
                "expected_contribution": 90,
                "actual_file": "tests/test_tracking_service_extended.py",
                "status": "implemented",
                "priority": "medium"
            },
            "test_medical_codes_api_comprehensive.py": {
                "expected_contribution": 100,
                "actual_file": "tests/test_medical_codes_api_comprehensive.py",
                "status": "implemented",
                "priority": "medium"
            },
            "test_external_services_extended.py": {
                "expected_contribution": 80,
                "actual_file": "tests/test_external_services_extended.py",
                "status": "implemented",
                "priority": "medium"
            },
            "test_database_operations.py": {
                "expected_contribution": 70,
                "actual_file": "tests/test_database_operations.py",
                "status": "implemented",
                "priority": "low"
            },
            "test_authentication_flows.py": {
                "expected_contribution": 60,
                "actual_file": "tests/test_authentication_flows.py",
                "status": "implemented",
                "priority": "low"
            },
            "test_configuration_management.py": {
                "expected_contribution": 40,
                "actual_file": "tests/test_configuration_management.py",
                "status": "implemented",
                "priority": "low"
            },
            "test_security_monitoring.py": {
                "expected_contribution": 40,
                "actual_file": "tests/test_security_monitoring.py",
                "status": "implemented",
                "priority": "low"
            },
            "test_utility_functions.py": {
                "expected_contribution": 30,
                "actual_file": "tests/test_utility_functions.py",
                "status": "implemented",
                "priority": "low"
            }
        }
    
    def analyze_current_state(self) -> Tuple[CoverageSnapshot, Dict]:
        """Analyze current coverage state and compare with baseline."""
        print("🔍 Analyzing current coverage state...")
        
        # Get current coverage
        current_snapshot = self.tracker.run_coverage_measurement()
        
        # Load baseline
        baseline = self.tracker.load_snapshot("baseline_24_percent")
        if not baseline:
            print("⚠️  No baseline found, using default values")
            baseline_coverage = self.baseline_coverage
            baseline_statements = int(15704 * (baseline_coverage / 100))
        else:
            baseline_coverage = baseline.overall_coverage
            baseline_statements = baseline.covered_statements
        
        # Calculate improvements
        coverage_improvement = current_snapshot.overall_coverage - baseline_coverage
        statements_improvement = current_snapshot.covered_statements - baseline_statements
        
        analysis = {
            "baseline_coverage": baseline_coverage,
            "current_coverage": current_snapshot.overall_coverage,
            "coverage_improvement": coverage_improvement,
            "baseline_statements": baseline_statements,
            "current_statements": current_snapshot.covered_statements,
            "statements_improvement": statements_improvement,
            "target_coverage": self.target_coverage,
            "target_reached": current_snapshot.overall_coverage >= self.target_coverage,
            "progress_percent": (coverage_improvement / (self.target_coverage - baseline_coverage)) * 100 if self.target_coverage > baseline_coverage else 0
        }
        
        print(f"✅ Analysis complete:")
        print(f"   Baseline: {baseline_coverage:.2f}% ({baseline_statements} statements)")
        print(f"   Current: {current_snapshot.overall_coverage:.2f}% ({current_snapshot.covered_statements} statements)")
        print(f"   Improvement: +{coverage_improvement:.2f}% (+{statements_improvement} statements)")
        print(f"   Target reached: {'YES' if analysis['target_reached'] else 'NO'}")
        
        return current_snapshot, analysis
    
    def analyze_test_file_contributions(self, current_snapshot: CoverageSnapshot, baseline_snapshot: Optional[CoverageSnapshot]) -> Dict:
        """Analyze contributions from each implemented test file."""
        print("\n📊 Analyzing test file contributions...")
        
        contributions = {
            "total_expected": sum(info["expected_contribution"] for info in self.implemented_test_files.values()),
            "files_implemented": 0,
            "files_missing": 0,
            "high_priority_implemented": 0,
            "medium_priority_implemented": 0,
            "low_priority_implemented": 0,
            "file_details": {}
        }
        
        for test_file, info in self.implemented_test_files.items():
            file_path = Path(info["actual_file"])
            exists = file_path.exists()
            
            if exists:
                contributions["files_implemented"] += 1
                if info["priority"] == "high":
                    contributions["high_priority_implemented"] += 1
                elif info["priority"] == "medium":
                    contributions["medium_priority_implemented"] += 1
                else:
                    contributions["low_priority_implemented"] += 1
            else:
                contributions["files_missing"] += 1
            
            contributions["file_details"][test_file] = {
                "exists": exists,
                "expected_contribution": info["expected_contribution"],
                "priority": info["priority"],
                "status": "implemented" if exists else "missing"
            }
        
        print(f"✅ Test file analysis complete:")
        print(f"   Files implemented: {contributions['files_implemented']}/{len(self.implemented_test_files)}")
        print(f"   High priority: {contributions['high_priority_implemented']}")
        print(f"   Medium priority: {contributions['medium_priority_implemented']}")
        print(f"   Low priority: {contributions['low_priority_implemented']}")
        print(f"   Total expected contribution: {contributions['total_expected']} statements")
        
        return contributions
    
    def analyze_module_improvements(self, current_snapshot: CoverageSnapshot, baseline_snapshot: Optional[CoverageSnapshot]) -> Dict:
        """Analyze module-level coverage improvements."""
        print("\n📈 Analyzing module-level improvements...")
        
        # Target modules from the design
        target_modules = {
            "src.services.decision_engine": {"target": 150, "priority": "high"},
            "src.api.llm_decisions": {"target": 120, "priority": "high"},
            "src.api.intake": {"target": 100, "priority": "high"},
            "src.services.validation": {"target": 80, "priority": "medium"},
            "src.services.tracking": {"target": 90, "priority": "medium"},
            "src.api.medical_codes": {"target": 100, "priority": "medium"},
            "src.services.external_services": {"target": 80, "priority": "medium"},
            "src.database.models": {"target": 70, "priority": "low"},
            "src.auth.oauth2": {"target": 60, "priority": "low"},
            "src.core.config": {"target": 40, "priority": "low"}
        }
        
        module_analysis = {
            "modules_analyzed": 0,
            "modules_improved": 0,
            "total_improvement": 0,
            "high_priority_improvement": 0,
            "medium_priority_improvement": 0,
            "low_priority_improvement": 0,
            "module_details": {},
            "top_performers": [],
            "needs_attention": []
        }
        
        if not baseline_snapshot:
            print("⚠️  No baseline available for module comparison")
            return module_analysis
        
        for module_name, target_info in target_modules.items():
            current_module = current_snapshot.modules.get(module_name)
            baseline_module = baseline_snapshot.modules.get(module_name)
            
            if current_module and baseline_module:
                improvement = current_module.statements_covered - baseline_module.statements_covered
                target = target_info["target"]
                priority = target_info["priority"]
                
                module_analysis["modules_analyzed"] += 1
                if improvement > 0:
                    module_analysis["modules_improved"] += 1
                    module_analysis["total_improvement"] += improvement
                    
                    if priority == "high":
                        module_analysis["high_priority_improvement"] += improvement
                    elif priority == "medium":
                        module_analysis["medium_priority_improvement"] += improvement
                    else:
                        module_analysis["low_priority_improvement"] += improvement
                
                progress_percent = (improvement / target) * 100 if target > 0 else 0
                
                module_details = {
                    "baseline_coverage": baseline_module.coverage_percent,
                    "current_coverage": current_module.coverage_percent,
                    "baseline_statements": baseline_module.statements_covered,
                    "current_statements": current_module.statements_covered,
                    "improvement": improvement,
                    "target": target,
                    "progress_percent": progress_percent,
                    "priority": priority
                }
                
                module_analysis["module_details"][module_name] = module_details
                
                # Categorize modules
                if improvement >= target * 0.8:  # 80% of target
                    module_analysis["top_performers"].append((module_name, module_details))
                elif improvement < target * 0.2:  # Less than 20% of target
                    module_analysis["needs_attention"].append((module_name, module_details))
        
        # Sort top performers by improvement
        module_analysis["top_performers"].sort(key=lambda x: x[1]["improvement"], reverse=True)
        module_analysis["needs_attention"].sort(key=lambda x: x[1]["improvement"])
        
        print(f"✅ Module analysis complete:")
        print(f"   Modules analyzed: {module_analysis['modules_analyzed']}")
        print(f"   Modules improved: {module_analysis['modules_improved']}")
        print(f"   Total improvement: {module_analysis['total_improvement']} statements")
        print(f"   Top performers: {len(module_analysis['top_performers'])}")
        print(f"   Need attention: {len(module_analysis['needs_attention'])}")
        
        return module_analysis
    
    def generate_recommendations(self, analysis: Dict, test_contributions: Dict, module_improvements: Dict) -> List[str]:
        """Generate recommendations for future coverage improvements."""
        recommendations = []
        
        # Overall progress recommendations
        if analysis["target_reached"]:
            recommendations.append("🎉 Congratulations! The 30% coverage target has been achieved.")
            recommendations.append("Consider setting a new target (e.g., 40%) for continued improvement.")
        else:
            remaining = analysis["target_coverage"] - analysis["current_coverage"]
            recommendations.append(f"📊 {remaining:.2f}% coverage still needed to reach the 30% target.")
            
            if analysis["progress_percent"] >= 80:
                recommendations.append("You're very close to the target. Focus on high-impact modules.")
            elif analysis["progress_percent"] >= 50:
                recommendations.append("Good progress made. Continue with the current strategy.")
            else:
                recommendations.append("Significant work still needed. Consider revising the approach.")
        
        # Test file recommendations
        if test_contributions["files_missing"] > 0:
            recommendations.append(f"⚠️  {test_contributions['files_missing']} test files are missing implementation.")
            recommendations.append("Prioritize implementing missing high-priority test files first.")
        
        # Module-specific recommendations
        if module_improvements["needs_attention"]:
            recommendations.append("🎯 Focus on these modules that need attention:")
  
            for module_name, details in module_improvements["needs_attention"][:3]:
                recommendations.append(f"   - {module_name} ({details['improvement']} statements, {details['progress_percent']:.1f}% of target)")
        
        # Strategy recommendations
        if analysis["progress_percent"] < 50:
            recommendations.append("📋 Consider these strategies:")
            recommendations.append("   - Focus on high-impact, low-complexity modules first")
            recommendations.append("   - Implement integration tests for end-to-end workflows")
            recommendations.append("   - Add unit tests for utility functions and helpers")
            recommendations.append("   - Review and improve existing test quality")
        
        return recommendations
    
    def generate_before_after_comparison(self, current_snapshot: CoverageSnapshot, baseline_snapshot: Optional[CoverageSnapshot]) -> Dict:
        """Generate detailed before/after comparison."""
        if not baseline_snapshot:
            return {"comparison_available": False, "reason": "no_baseline"}
        
        comparison = {
            "comparison_available": True,
            "timeline": {
                "baseline_date": baseline_snapshot.timestamp,
                "current_date": current_snapshot.timestamp
            },
            "overall_metrics": {
                "coverage_before": baseline_snapshot.overall_coverage,
                "coverage_after": current_snapshot.overall_coverage,
                "coverage_change": current_snapshot.overall_coverage - baseline_snapshot.overall_coverage,
                "statements_before": baseline_snapshot.covered_statements,
                "statements_after": current_snapshot.covered_statements,
                "statements_change": current_snapshot.covered_statements - baseline_snapshot.covered_statements,
                "total_statements": current_snapshot.total_statements
            },
            "test_metrics": {
                "test_files_before": baseline_snapshot.test_files_count,
                "test_files_after": current_snapshot.test_files_count,
                "test_files_added": current_snapshot.test_files_count - baseline_snapshot.test_files_count
            },
            "module_changes": []
        }
        
        # Analyze module-level changes
        for module_name in set(list(current_snapshot.modules.keys()) + list(baseline_snapshot.modules.keys())):
            current_module = current_snapshot.modules.get(module_name)
            baseline_module = baseline_snapshot.modules.get(module_name)
            
            if current_module and baseline_module:
                coverage_change = current_module.coverage_percent - baseline_module.coverage_percent
                statements_change = current_module.statements_covered - baseline_module.statements_covered
                
                if abs(coverage_change) > 0.1 or abs(statements_change) > 0:  # Only include modules with changes
                    comparison["module_changes"].append({
                        "module": module_name,
                        "coverage_before": baseline_module.coverage_percent,
                        "coverage_after": current_module.coverage_percent,
                        "coverage_change": coverage_change,
                        "statements_before": baseline_module.statements_covered,
                        "statements_after": current_module.statements_covered,
                        "statements_change": statements_change
                    })
        
        # Sort by statements change (descending)
        comparison["module_changes"].sort(key=lambda x: x["statements_change"], reverse=True)
        
        return comparison
    
    def generate_comprehensive_report(self, current_snapshot: CoverageSnapshot, analysis: Dict, 
                                    test_contributions: Dict, module_improvements: Dict, 
                                    comparison: Dict, recommendations: List[str]) -> str:
        """Generate the comprehensive final report."""
        report_lines = []
        
        # Header
        report_lines.append("=" * 100)
        report_lines.append("FINAL COVERAGE IMPROVEMENT REPORT")
        report_lines.append("=" * 100)
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"Project: Prior Authorization Agent - Healthcare Coverage System")
        report_lines.append("")
        
        # Executive Summary
        report_lines.append("EXECUTIVE SUMMARY")
        report_lines.append("-" * 50)
        target_status = "✅ ACHIEVED" if analysis["target_reached"] else "❌ IN PROGRESS"
        report_lines.append(f"Coverage Target (30%): {target_status}")
        report_lines.append(f"Current Coverage: {analysis['current_coverage']:.2f}%")
        report_lines.append(f"Baseline Coverage: {analysis['baseline_coverage']:.2f}%")
        report_lines.append(f"Total Improvement: +{analysis['coverage_improvement']:.2f}% ({analysis['statements_improvement']:+d} statements)")
        report_lines.append(f"Progress Toward Target: {analysis['progress_percent']:.1f}%")
        report_lines.append("")
        
        # Test Implementation Status
        report_lines.append("TEST IMPLEMENTATION STATUS")
        report_lines.append("-" * 50)
        report_lines.append(f"Test Files Implemented: {test_contributions['files_implemented']}/{len(self.implemented_test_files)}")
        report_lines.append(f"Expected Total Contribution: {test_contributions['total_expected']} statements")
        report_lines.append("")
        
        # Priority breakdown
        report_lines.append("Implementation by Priority:")
        report_lines.append(f"  High Priority:   {test_contributions['high_priority_implemented']}/3 files")
        report_lines.append(f"  Medium Priority: {test_contributions['medium_priority_implemented']}/4 files")
        report_lines.append(f"  Low Priority:    {test_contributions['low_priority_implemented']}/5 files")
        report_lines.append("")
        
        # Detailed test file status
        report_lines.append("Detailed Test File Status:")
        for test_file, details in test_contributions["file_details"].items():
            status_icon = "✅" if details["exists"] else "❌"
            priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}[details["priority"]]
            report_lines.append(f"  {status_icon} {priority_icon} {test_file} (expected: +{details['expected_contribution']} statements)")
        report_lines.append("")
        
        # Module-Level Analysis
        if module_improvements.get("modules_analyzed", 0) > 0:
            report_lines.append("MODULE-LEVEL COVERAGE IMPROVEMENTS")
            report_lines.append("-" * 50)
            report_lines.append(f"Modules Analyzed: {module_improvements['modules_analyzed']}")
            report_lines.append(f"Modules with Improvements: {module_improvements['modules_improved']}")
            report_lines.append(f"Total Statement Improvements: {module_improvements['total_improvement']}")
            report_lines.append("")
            
            # Priority breakdown
            report_lines.append("Improvements by Priority:")
            report_lines.append(f"  High Priority:   {module_improvements['high_priority_improvement']} statements")
            report_lines.append(f"  Medium Priority: {module_improvements['medium_priority_improvement']} statements")
            report_lines.append(f"  Low Priority:    {module_improvements['low_priority_improvement']} statements")
            report_lines.append("")
            
            # Top performing modules
            if module_improvements["top_performers"]:
                report_lines.append("Top Performing Modules:")
                for module_name, details in module_improvements["top_performers"][:5]:
                    report_lines.append(f"  ✅ {module_name}: +{details['improvement']} statements ({details['progress_percent']:.1f}% of target)")
                report_lines.append("")
            
            # Modules needing attention
            if module_improvements["needs_attention"]:
                report_lines.append("Modules Needing Attention:")
                for module_name, details in module_improvements["needs_attention"][:5]:
                    report_lines.append(f"  ⚠️  {module_name}: +{details['improvement']} statements ({details['progress_percent']:.1f}% of target)")
                report_lines.append("")
        
        # Before/After Comparison
        if comparison.get("comparison_available"):
            report_lines.append("BEFORE/AFTER COMPARISON")
            report_lines.append("-" * 50)
            
            overall = comparison["overall_metrics"]
            report_lines.append(f"Coverage: {overall['coverage_before']:.2f}% → {overall['coverage_after']:.2f}% ({overall['coverage_change']:+.2f}%)")
            report_lines.append(f"Covered Statements: {overall['statements_before']} → {overall['statements_after']} ({overall['statements_change']:+d})")
            report_lines.append(f"Total Statements: {overall['total_statements']}")
            
            test_metrics = comparison["test_metrics"]
            report_lines.append(f"Test Files: {test_metrics['test_files_before']} → {test_metrics['test_files_after']} ({test_metrics['test_files_added']:+d})")
            report_lines.append("")
            
            # Top module changes
            if comparison["module_changes"]:
                report_lines.append("Top Module Changes:")
                for change in comparison["module_changes"][:10]:
                    if change["statements_change"] != 0:
                        report_lines.append(f"  {change['module']}: {change['coverage_before']:.1f}% → {change['coverage_after']:.1f}% ({change['statements_change']:+d} statements)")
                report_lines.append("")
        
        # Requirements Validation
        report_lines.append("REQUIREMENTS VALIDATION")
        report_lines.append("-" * 50)
        req_1_1 = "✅ PASSED" if analysis["target_reached"] else "❌ IN PROGRESS"
        req_1_2 = "✅ PASSED" if analysis["coverage_improvement"] >= 6.0 else "❌ IN PROGRESS"
        req_5_2 = "✅ PASSED"  # This report itself fulfills this requirement
        req_5_3 = "✅ PASSED" if module_improvements.get("modules_analyzed", 0) > 0 else "❌ INCOMPLETE"
        req_5_4 = "✅ PASSED"  # Recommendations are provided
        
        report_lines.append(f"Requirement 1.1 (30% Coverage Target): {req_1_1}")
        report_lines.append(f"Requirement 1.2 (6% Coverage Increase): {req_1_2}")
        report_lines.append(f"Requirement 5.2 (Coverage Documentation): {req_5_2}")
        report_lines.append(f"Requirement 5.3 (Module-level Tracking): {req_5_3}")
        report_lines.append(f"Requirement 5.4 (Future Recommendations): {req_5_4}")
        report_lines.append("")
        
        # Recommendations
        report_lines.append("RECOMMENDATIONS FOR FUTURE IMPROVEMENTS")
        report_lines.append("-" * 50)
        for recommendation in recommendations:
            report_lines.append(recommendation)
        report_lines.append("")
        
        # Technical Details
        report_lines.append("TECHNICAL DETAILS")
        report_lines.append("-" * 50)
        report_lines.append(f"Measurement Date: {current_snapshot.timestamp}")
        report_lines.append(f"Execution Time: {current_snapshot.execution_time_seconds:.1f} seconds")
        report_lines.append(f"Total Test Files: {current_snapshot.test_files_count}")
        report_lines.append(f"Coverage Tool: pytest-cov")
        report_lines.append(f"Python Version: 3.13+")
        report_lines.append("")
        
        # Footer
        report_lines.append("=" * 100)
        report_lines.append("End of Report")
        report_lines.append("=" * 100)
        
        return "\n".join(report_lines)
    
    def save_report(self, report_content: str, format_type: str = "markdown") -> Path:
        """Save the final report to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if format_type == "markdown":
            filename = f"final_coverage_report_{timestamp}.md"
        else:
            filename = f"final_coverage_report_{timestamp}.txt"
        
        filepath = Path("tests/coverage_reports") / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w') as f:
            f.write(report_content)
        
        print(f"📄 Final coverage report saved to: {filepath}")
        return filepath
    
    def generate_json_summary(self, current_snapshot: CoverageSnapshot, analysis: Dict, 
                            test_contributions: Dict, module_improvements: Dict) -> Dict:
        """Generate JSON summary for programmatic use."""
        return {
            "report_metadata": {
                "generated_at": datetime.now().isoformat(),
                "report_type": "final_coverage_improvement",
                "version": "1.0"
            },
            "coverage_summary": {
                "baseline_coverage": analysis["baseline_coverage"],
                "current_coverage": analysis["current_coverage"],
                "target_coverage": analysis["target_coverage"],
                "improvement": analysis["coverage_improvement"],
                "target_reached": analysis["target_reached"],
                "progress_percent": analysis["progress_percent"]
            },
            "test_implementation": {
                "total_files": len(self.implemented_test_files),
                "implemented_files": test_contributions["files_implemented"],
                "missing_files": test_contributions["files_missing"],
                "expected_contribution": test_contributions["total_expected"]
            },
            "module_improvements": {
                "analyzed": module_improvements.get("modules_analyzed", 0),
                "improved": module_improvements.get("modules_improved", 0),
                "total_improvement": module_improvements.get("total_improvement", 0)
            },
            "requirements_status": {
                "req_1_1_30_percent": analysis["target_reached"],
                "req_1_2_6_percent_increase": analysis["coverage_improvement"] >= 6.0,
                "req_5_2_documentation": True,
                "req_5_3_module_tracking": module_improvements.get("modules_analyzed", 0) > 0,
                "req_5_4_recommendations": True
            }
        }


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description="Generate final coverage improvement report")
    parser.add_argument("--format", choices=["markdown", "text"], default="markdown",
                       help="Output format for the report")
    parser.add_argument("--json-summary", action="store_true",
                       help="Also generate JSON summary")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Verbose output during generation")
    
    args = parser.parse_args()
    
    generator = FinalCoverageReportGenerator()
    
    try:
        print("🚀 Generating final coverage improvement report...")
        print("=" * 80)
        
        # Step 1: Analyze current state
        current_snapshot, analysis = generator.analyze_current_state()
        
        # Step 2: Analyze test file contributions
        baseline_snapshot = generator.tracker.load_snapshot("baseline_24_percent")
        test_contributions = generator.analyze_test_file_contributions(current_snapshot, baseline_snapshot)
        
        # Step 3: Analyze module improvements
        module_improvements = generator.analyze_module_improvements(current_snapshot, baseline_snapshot)
        
        # Step 4: Generate before/after comparison
        comparison = generator.generate_before_after_comparison(current_snapshot, baseline_snapshot)
        
        # Step 5: Generate recommendations
        recommendations = generator.generate_recommendations(analysis, test_contributions, module_improvements)
        
        # Step 6: Generate comprehensive report
        report_content = generator.generate_comprehensive_report(
            current_snapshot, analysis, test_contributions, 
            module_improvements, comparison, recommendations
        )
        
        # Step 7: Save report
        report_path = generator.save_report(report_content, args.format)
        
        # Step 8: Generate JSON summary if requested
        if args.json_summary:
            json_summary = generator.generate_json_summary(
                current_snapshot, analysis, test_contributions, module_improvements
            )
            json_path = report_path.with_suffix('.json')
            with open(json_path, 'w') as f:
                json.dump(json_summary, f, indent=2)
            print(f"📊 JSON summary saved to: {json_path}")
        
        # Final status
        print("\n" + "=" * 80)
        if analysis["target_reached"]:
            print("🎉 SUCCESS: Coverage target achieved! Report generated successfully.")
            sys.exit(0)
        else:
            progress = analysis["progress_percent"]
            if progress >= 80:
                print("✅ EXCELLENT PROGRESS: Very close to target. Report generated successfully.")
                sys.exit(0)
            elif progress >= 50:
                print("📊 GOOD PROGRESS: Halfway to target. Report generated successfully.")
                sys.exit(0)
            else:
                print("⚠️  NEEDS WORK: Significant effort still required. Report generated successfully.")
                sys.exit(0)
                
    except Exception as e:
        print(f"\n❌ REPORT GENERATION FAILED: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()