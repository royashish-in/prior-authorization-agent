"""
Coverage reporting utilities for automated progress tracking.

This module provides functionality to generate detailed coverage reports,
track progress toward the 30% target, and create documentation for improvements.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from .baseline_tracker import CoverageSnapshot, CoverageTracker, ModuleCoverage


@dataclass
class ModuleTargetProgress:
    """Progress tracking for a specific module target."""
    module_name: str
    baseline_coverage: float
    current_coverage: float
    target_coverage: float
    statements_baseline: int
    statements_current: int
    statements_target: int
    progress_percent: float
    on_track: bool


@dataclass
class CoverageImprovementReport:
    """Comprehensive coverage improvement report."""
    report_id: str
    timestamp: str
    baseline_snapshot: CoverageSnapshot
    current_snapshot: CoverageSnapshot
    overall_progress: Dict
    module_progress: List[ModuleTargetProgress]
    test_files_added: List[str]
    recommendations: List[str]
    next_targets: List[str]


class CoverageReporter:
    """Generate comprehensive coverage reports and track progress."""
    
    def __init__(self, tracker: CoverageTracker = None):
        self.tracker = tracker or CoverageTracker()
        self.reports_dir = Path("tests/coverage_reports")
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        
        # Module targets based on the design document
        self.module_targets = {
            "src.services.decision_engine": {"target_increase": 150, "priority": 1},
            "src.api.llm_decisions": {"target_increase": 120, "priority": 2},
            "src.api.intake": {"target_increase": 100, "priority": 3},
            "src.services.validation": {"target_increase": 80, "priority": 4},
            "src.services.tracking": {"target_increase": 90, "priority": 5},
            "src.api.medical_codes": {"target_increase": 100, "priority": 6},
            "src.services.external_services": {"target_increase": 80, "priority": 7},
            "src.database.models": {"target_increase": 70, "priority": 8},
            "src.auth.oauth2": {"target_increase": 60, "priority": 9},
            "src.core.config": {"target_increase": 40, "priority": 10}
        }
    
    def generate_comprehensive_report(self, test_files_added: List[str] = None) -> CoverageImprovementReport:
        """Generate a comprehensive coverage improvement report."""
        # Get current snapshot
        current_snapshot = self.tracker.run_coverage_measurement()
        
        # Load baseline
        baseline_snapshot = self.tracker.load_snapshot("baseline_24_percent")
        if not baseline_snapshot:
            baseline_snapshot = self.tracker.establish_baseline()
        
        # Calculate overall progress
        overall_progress = self._calculate_overall_progress(baseline_snapshot, current_snapshot)
        
        # Calculate module progress
        module_progress = self._calculate_module_progress(baseline_snapshot, current_snapshot)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(current_snapshot, module_progress)
        
        # Identify next targets
        next_targets = self._identify_next_targets(module_progress)
        
        report = CoverageImprovementReport(
            report_id=f"coverage_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            baseline_snapshot=baseline_snapshot,
            current_snapshot=current_snapshot,
            overall_progress=overall_progress,
            module_progress=module_progress,
            test_files_added=test_files_added or [],
            recommendations=recommendations,
            next_targets=next_targets
        )
        
        return report
    
    def _calculate_overall_progress(self, baseline: CoverageSnapshot, current: CoverageSnapshot) -> Dict:
        """Calculate overall progress metrics."""
        coverage_increase = current.overall_coverage - baseline.overall_coverage
        statements_increase = current.covered_statements - baseline.covered_statements
        
        target_coverage = 30.0
        target_increase_needed = target_coverage - baseline.overall_coverage
        progress_percent = (coverage_increase / target_increase_needed) * 100 if target_increase_needed > 0 else 0
        
        return {
            "baseline_coverage": baseline.overall_coverage,
            "current_coverage": current.overall_coverage,
            "target_coverage": target_coverage,
            "coverage_increase": coverage_increase,
            "statements_increase": statements_increase,
            "progress_percent": progress_percent,
            "remaining_coverage": max(0, target_coverage - current.overall_coverage),
            "remaining_statements": max(0, 900 - statements_increase),  # Approximate target
            "on_track": progress_percent >= 50,  # Arbitrary threshold for "on track"
            "execution_time": current.execution_time_seconds
        }
    
    def _calculate_module_progress(self, baseline: CoverageSnapshot, current: CoverageSnapshot) -> List[ModuleTargetProgress]:
        """Calculate progress for each target module."""
        module_progress = []
        
        for module_name, target_info in self.module_targets.items():
            baseline_module = baseline.modules.get(module_name)
            current_module = current.modules.get(module_name)
            
            if not baseline_module or not current_module:
                continue
            
            target_statements = baseline_module.statements_covered + target_info["target_increase"]
            target_coverage = (target_statements / baseline_module.statements_total) * 100 if baseline_module.statements_total > 0 else 0
            
            statements_progress = current_module.statements_covered - baseline_module.statements_covered
            progress_percent = (statements_progress / target_info["target_increase"]) * 100 if target_info["target_increase"] > 0 else 0
            
            module_progress.append(ModuleTargetProgress(
                module_name=module_name,
                baseline_coverage=baseline_module.coverage_percent,
                current_coverage=current_module.coverage_percent,
                target_coverage=min(target_coverage, 100.0),  # Cap at 100%
                statements_baseline=baseline_module.statements_covered,
                statements_current=current_module.statements_covered,
                statements_target=target_statements,
                progress_percent=progress_percent,
                on_track=progress_percent >= 25  # Arbitrary threshold
            ))
        
        # Sort by priority
        module_progress.sort(key=lambda x: self.module_targets.get(x.module_name, {}).get("priority", 999))
        
        return module_progress
    
    def _generate_recommendations(self, current: CoverageSnapshot, module_progress: List[ModuleTargetProgress]) -> List[str]:
        """Generate recommendations based on current progress."""
        recommendations = []
        
        # Overall progress recommendations
        if current.overall_coverage < 27:
            recommendations.append("Focus on high-impact modules to accelerate progress toward 30% target")
        elif current.overall_coverage < 29:
            recommendations.append("Continue steady progress - you're close to the 30% target")
        else:
            recommendations.append("Excellent progress! Consider setting a higher target for continued improvement")
        
        # Module-specific recommendations
        underperforming_modules = [m for m in module_progress if m.progress_percent < 25]
        if underperforming_modules:
            recommendations.append(f"Priority modules needing attention: {', '.join([m.module_name.split('.')[-1] for m in underperforming_modules[:3]])}")
        
        # Test execution performance
        if current.execution_time_seconds > 60:
            recommendations.append("Consider optimizing test execution time - currently exceeding 60-second target")
        
        # Coverage distribution
        high_coverage_modules = [name for name, module in current.modules.items() if module.coverage_percent > 80]
        if len(high_coverage_modules) < 5:
            recommendations.append("Consider adding tests to modules with very low coverage for balanced improvement")
        
        return recommendations
    
    def _identify_next_targets(self, module_progress: List[ModuleTargetProgress]) -> List[str]:
        """Identify the next modules to target for testing."""
        # Find modules with low progress that are high priority
        next_targets = []
        
        for module in module_progress[:5]:  # Top 5 priority modules
            if module.progress_percent < 50:
                next_targets.append(f"{module.module_name} (current: {module.current_coverage:.1f}%, target: {module.target_coverage:.1f}%)")
        
        return next_targets
    
    def save_report(self, report: CoverageImprovementReport) -> Path:
        """Save coverage improvement report to file."""
        report_data = {
            "report_id": report.report_id,
            "timestamp": report.timestamp,
            "baseline_snapshot": report.baseline_snapshot.to_dict(),
            "current_snapshot": report.current_snapshot.to_dict(),
            "overall_progress": report.overall_progress,
            "module_progress": [
                {
                    "module_name": m.module_name,
                    "baseline_coverage": m.baseline_coverage,
                    "current_coverage": m.current_coverage,
                    "target_coverage": m.target_coverage,
                    "statements_baseline": m.statements_baseline,
                    "statements_current": m.statements_current,
                    "statements_target": m.statements_target,
                    "progress_percent": m.progress_percent,
                    "on_track": m.on_track
                }
                for m in report.module_progress
            ],
            "test_files_added": report.test_files_added,
            "recommendations": report.recommendations,
            "next_targets": report.next_targets
        }
        
        filepath = self.reports_dir / f"{report.report_id}.json"
        with open(filepath, 'w') as f:
            json.dump(report_data, f, indent=2)
        
        return filepath
    
    def generate_markdown_report(self, report: CoverageImprovementReport) -> str:
        """Generate a markdown-formatted report."""
        md_lines = []
        
        # Header
        md_lines.append(f"# Coverage Improvement Report")
        md_lines.append(f"**Report ID:** {report.report_id}")
        md_lines.append(f"**Generated:** {report.timestamp}")
        md_lines.append("")
        
        # Overall Progress
        md_lines.append("## Overall Progress")
        progress = report.overall_progress
        md_lines.append(f"- **Current Coverage:** {progress['current_coverage']:.2f}%")
        md_lines.append(f"- **Baseline Coverage:** {progress['baseline_coverage']:.2f}%")
        md_lines.append(f"- **Target Coverage:** {progress['target_coverage']:.2f}%")
        md_lines.append(f"- **Coverage Increase:** +{progress['coverage_increase']:.2f}%")
        md_lines.append(f"- **Statements Added:** +{progress['statements_increase']}")
        md_lines.append(f"- **Progress Toward Target:** {progress['progress_percent']:.1f}%")
        md_lines.append(f"- **Remaining Coverage Needed:** {progress['remaining_coverage']:.2f}%")
        md_lines.append(f"- **Status:** {'✅ On Track' if progress['on_track'] else '⚠️ Needs Attention'}")
        md_lines.append("")
        
        # Module Progress
        md_lines.append("## Module Progress")
        md_lines.append("| Module | Baseline | Current | Target | Progress | Status |")
        md_lines.append("|--------|----------|---------|--------|----------|--------|")
        
        for module in report.module_progress[:10]:  # Top 10 modules
            status = "✅" if module.on_track else "⚠️"
            module_short = module.module_name.split('.')[-1]
            md_lines.append(f"| {module_short} | {module.baseline_coverage:.1f}% | {module.current_coverage:.1f}% | {module.target_coverage:.1f}% | {module.progress_percent:.1f}% | {status} |")
        
        md_lines.append("")
        
        # Test Files Added
        if report.test_files_added:
            md_lines.append("## Test Files Added")
            for test_file in report.test_files_added:
                md_lines.append(f"- {test_file}")
            md_lines.append("")
        
        # Recommendations
        if report.recommendations:
            md_lines.append("## Recommendations")
            for rec in report.recommendations:
                md_lines.append(f"- {rec}")
            md_lines.append("")
        
        # Next Targets
        if report.next_targets:
            md_lines.append("## Next Priority Targets")
            for target in report.next_targets:
                md_lines.append(f"- {target}")
            md_lines.append("")
        
        # Performance Metrics
        md_lines.append("## Performance Metrics")
        md_lines.append(f"- **Test Execution Time:** {progress['execution_time']:.1f}s")
        md_lines.append(f"- **Total Test Files:** {report.current_snapshot.test_files_count}")
        md_lines.append(f"- **Total Modules Tracked:** {len(report.current_snapshot.modules)}")
        
        return "\n".join(md_lines)
    
    def save_markdown_report(self, report: CoverageImprovementReport) -> Path:
        """Save markdown report to file."""
        markdown_content = self.generate_markdown_report(report)
        filepath = self.reports_dir / f"{report.report_id}.md"
        
        with open(filepath, 'w') as f:
            f.write(markdown_content)
        
        return filepath
    
    def generate_quick_status(self) -> str:
        """Generate a quick status summary."""
        current_snapshot = self.tracker.run_coverage_measurement()
        baseline_snapshot = self.tracker.load_snapshot("baseline_24_percent")
        
        if not baseline_snapshot:
            return "No baseline found. Run establish_baseline() first."
        
        coverage_increase = current_snapshot.overall_coverage - baseline_snapshot.overall_coverage
        statements_increase = current_snapshot.covered_statements - baseline_snapshot.covered_statements
        
        target_progress = (coverage_increase / (30.0 - baseline_snapshot.overall_coverage)) * 100
        
        status_lines = [
            f"📊 Coverage Status: {current_snapshot.overall_coverage:.2f}% (+{coverage_increase:.2f}%)",
            f"📈 Statements Added: +{statements_increase}",
            f"🎯 Progress to 30%: {target_progress:.1f}%",
            f"⏱️ Last Execution: {current_snapshot.execution_time_seconds:.1f}s"
        ]
        
        return "\n".join(status_lines)


def get_coverage_reporter() -> CoverageReporter:
    """Get the global coverage reporter instance."""
    return CoverageReporter()