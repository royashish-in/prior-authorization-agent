"""
Coverage baseline tracking and measurement utilities.

This module provides functionality to establish coverage baselines,
track incremental improvements, and validate progress toward targets.
"""

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict


@dataclass
class ModuleCoverage:
    """Coverage information for a single module."""
    module_name: str
    statements_total: int
    statements_covered: int
    coverage_percent: float
    missing_lines: List[int]
    
    @property
    def statements_missing(self) -> int:
        """Calculate number of missing statements."""
        return self.statements_total - self.statements_covered


@dataclass
class CoverageSnapshot:
    """Complete coverage snapshot at a point in time."""
    timestamp: str
    total_statements: int
    covered_statements: int
    overall_coverage: float
    modules: Dict[str, ModuleCoverage]
    test_files_count: int
    execution_time_seconds: float
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "total_statements": self.total_statements,
            "covered_statements": self.covered_statements,
            "overall_coverage": self.overall_coverage,
            "modules": {name: asdict(module) for name, module in self.modules.items()},
            "test_files_count": self.test_files_count,
            "execution_time_seconds": self.execution_time_seconds
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'CoverageSnapshot':
        """Create from dictionary loaded from JSON."""
        modules = {}
        for name, module_data in data["modules"].items():
            modules[name] = ModuleCoverage(**module_data)
        
        return cls(
            timestamp=data["timestamp"],
            total_statements=data["total_statements"],
            covered_statements=data["covered_statements"],
            overall_coverage=data["overall_coverage"],
            modules=modules,
            test_files_count=data["test_files_count"],
            execution_time_seconds=data["execution_time_seconds"]
        )


class CoverageTracker:
    """Main coverage tracking utility."""
    
    def __init__(self, reports_dir: str = "tests/coverage_reports"):
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        
        # Coverage target configuration
        self.target_coverage = 30.0
        self.baseline_coverage = 24.27
        self.target_statements_increase = 900  # Approximately 6% of 15,704 total
        
    def run_coverage_measurement(self, test_pattern: str = "tests/") -> CoverageSnapshot:
        """
        Run coverage measurement and return snapshot.
        
        Args:
            test_pattern: Pattern for tests to run (default: all tests)
            
        Returns:
            CoverageSnapshot with current coverage data
        """
        start_time = time.time()
        
        # Run pytest with coverage
        cmd = [
            "python", "-m", "pytest",
            test_pattern,
            "--cov=src",
            "--cov-report=json:coverage.json",
            "--cov-report=term-missing",
            "-q"  # Quiet mode for faster execution
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            execution_time = time.time() - start_time
            
            if result.returncode != 0:
                print(f"Warning: Tests failed but continuing with coverage analysis")
                print(f"STDERR: {result.stderr}")
            
            # Load coverage data
            coverage_data = self._load_coverage_json()
            snapshot = self._create_snapshot(coverage_data, execution_time)
            
            return snapshot
            
        except subprocess.TimeoutExpired:
            raise RuntimeError("Coverage measurement timed out after 5 minutes")
        except Exception as e:
            raise RuntimeError(f"Failed to run coverage measurement: {e}")
    
    def _load_coverage_json(self) -> Dict:
        """Load coverage data from JSON report."""
        coverage_file = Path("coverage.json")
        if not coverage_file.exists():
            raise FileNotFoundError("Coverage JSON report not found")
        
        with open(coverage_file, 'r') as f:
            return json.load(f)
    
    def _create_snapshot(self, coverage_data: Dict, execution_time: float) -> CoverageSnapshot:
        """Create coverage snapshot from coverage data."""
        files_data = coverage_data.get("files", {})
        totals = coverage_data.get("totals", {})
        
        modules = {}
        for file_path, file_data in files_data.items():
            # Only include src/ modules
            if not file_path.startswith("src/"):
                continue
                
            module_name = file_path.replace("/", ".").replace(".py", "")
            
            # Get missing lines
            missing_lines = file_data.get("missing_lines", [])
            
            modules[module_name] = ModuleCoverage(
                module_name=module_name,
                statements_total=file_data.get("num_statements", 0),
                statements_covered=file_data.get("num_statements", 0) - len(missing_lines),
                coverage_percent=file_data.get("summary", {}).get("percent_covered", 0.0),
                missing_lines=missing_lines
            )
        
        # Count test files
        test_files_count = len([f for f in Path("tests").rglob("test_*.py")])
        
        return CoverageSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_statements=totals.get("num_statements", 0),
            covered_statements=totals.get("covered_lines", 0),
            overall_coverage=totals.get("percent_covered", 0.0),
            modules=modules,
            test_files_count=test_files_count,
            execution_time_seconds=execution_time
        )
    
    def save_snapshot(self, snapshot: CoverageSnapshot, filename: str) -> Path:
        """Save coverage snapshot to file."""
        filepath = self.reports_dir / f"{filename}.json"
        
        with open(filepath, 'w') as f:
            json.dump(snapshot.to_dict(), f, indent=2)
        
        print(f"Coverage snapshot saved to {filepath}")
        return filepath
    
    def load_snapshot(self, filename: str) -> Optional[CoverageSnapshot]:
        """Load coverage snapshot from file."""
        filepath = self.reports_dir / f"{filename}.json"
        
        if not filepath.exists():
            return None
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        return CoverageSnapshot.from_dict(data)
    
    def establish_baseline(self) -> CoverageSnapshot:
        """Establish baseline coverage measurement."""
        print("Establishing coverage baseline...")
        snapshot = self.run_coverage_measurement()
        self.save_snapshot(snapshot, "baseline_24_percent")
        
        print(f"Baseline established:")
        print(f"  Overall coverage: {snapshot.overall_coverage:.2f}%")
        print(f"  Total statements: {snapshot.total_statements}")
        print(f"  Covered statements: {snapshot.covered_statements}")
        print(f"  Test files: {snapshot.test_files_count}")
        
        return snapshot
    
    def measure_incremental_progress(self, test_file_added: str = None) -> Tuple[CoverageSnapshot, Dict]:
        """
        Measure incremental coverage progress.
        
        Args:
            test_file_added: Name of test file that was added (for tracking)
            
        Returns:
            Tuple of (current_snapshot, progress_report)
        """
        print("Measuring incremental coverage progress...")
        current_snapshot = self.run_coverage_measurement()
        
        # Load baseline for comparison
        baseline = self.load_snapshot("baseline_24_percent")
        if not baseline:
            print("Warning: No baseline found, establishing new baseline")
            baseline = self.establish_baseline()
        
        # Calculate progress
        progress_report = self._calculate_progress(baseline, current_snapshot, test_file_added)
        
        # Save incremental snapshot
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.save_snapshot(current_snapshot, f"incremental_{timestamp}")
        
        return current_snapshot, progress_report
    
    def _calculate_progress(self, baseline: CoverageSnapshot, current: CoverageSnapshot, 
                          test_file_added: str = None) -> Dict:
        """Calculate progress between two snapshots."""
        coverage_increase = current.overall_coverage - baseline.overall_coverage
        statements_increase = current.covered_statements - baseline.covered_statements
        
        # Calculate progress toward target
        target_increase_needed = self.target_coverage - baseline.overall_coverage
        progress_percent = (coverage_increase / target_increase_needed) * 100 if target_increase_needed > 0 else 0
        
        # Find modules with biggest improvements
        module_improvements = []
        for module_name, current_module in current.modules.items():
            baseline_module = baseline.modules.get(module_name)
            if baseline_module:
                improvement = current_module.statements_covered - baseline_module.statements_covered
                if improvement > 0:
                    module_improvements.append({
                        "module": module_name,
                        "statements_added": improvement,
                        "coverage_increase": current_module.coverage_percent - baseline_module.coverage_percent
                    })
        
        # Sort by statements added
        module_improvements.sort(key=lambda x: x["statements_added"], reverse=True)
        
        progress_report = {
            "test_file_added": test_file_added,
            "coverage_increase": coverage_increase,
            "statements_increase": statements_increase,
            "progress_toward_target_percent": progress_percent,
            "remaining_coverage_needed": max(0, self.target_coverage - current.overall_coverage),
            "remaining_statements_needed": max(0, self.target_statements_increase - statements_increase),
            "top_module_improvements": module_improvements[:10],
            "execution_time": current.execution_time_seconds,
            "timestamp": current.timestamp
        }
        
        return progress_report
    
    def generate_progress_report(self, progress_data: Dict) -> str:
        """Generate human-readable progress report."""
        report = []
        report.append("=== Coverage Progress Report ===")
        report.append(f"Timestamp: {progress_data['timestamp']}")
        
        if progress_data.get('test_file_added'):
            report.append(f"Test file added: {progress_data['test_file_added']}")
        
        report.append(f"Coverage increase: +{progress_data['coverage_increase']:.2f}%")
        report.append(f"Statements added: +{progress_data['statements_increase']}")
        report.append(f"Progress toward 30% target: {progress_data['progress_toward_target_percent']:.1f}%")
        report.append(f"Remaining coverage needed: {progress_data['remaining_coverage_needed']:.2f}%")
        report.append(f"Remaining statements needed: ~{progress_data['remaining_statements_needed']}")
        
        if progress_data['top_module_improvements']:
            report.append("\nTop Module Improvements:")
            for improvement in progress_data['top_module_improvements'][:5]:
                report.append(f"  {improvement['module']}: +{improvement['statements_added']} statements "
                            f"(+{improvement['coverage_increase']:.1f}%)")
        
        report.append(f"\nExecution time: {progress_data['execution_time']:.1f}s")
        
        return "\n".join(report)
    
    def validate_target_reached(self) -> Tuple[bool, Dict]:
        """
        Validate if the 30% coverage target has been reached.
        
        Returns:
            Tuple of (target_reached, validation_report)
        """
        current_snapshot = self.run_coverage_measurement()
        baseline = self.load_snapshot("baseline_24_percent")
        
        target_reached = current_snapshot.overall_coverage >= self.target_coverage
        
        validation_report = {
            "target_reached": target_reached,
            "current_coverage": current_snapshot.overall_coverage,
            "target_coverage": self.target_coverage,
            "baseline_coverage": baseline.overall_coverage if baseline else 0,
            "total_improvement": current_snapshot.overall_coverage - (baseline.overall_coverage if baseline else 0),
            "statements_improvement": current_snapshot.covered_statements - (baseline.covered_statements if baseline else 0),
            "validation_timestamp": current_snapshot.timestamp
        }
        
        return target_reached, validation_report


def get_coverage_tracker() -> CoverageTracker:
    """Get the global coverage tracker instance."""
    return CoverageTracker()