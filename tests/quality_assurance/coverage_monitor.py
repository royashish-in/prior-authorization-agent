#!/usr/bin/env python3
"""
Automated coverage monitoring and reporting system for the Prior Authorization System test suite.

This module provides comprehensive coverage analysis, trend monitoring, and automated
reporting capabilities to ensure test coverage meets quality standards.
"""

import os
import json
import sqlite3
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class CoverageMetrics:
    """Coverage metrics for a specific time period."""
    timestamp: str
    overall_coverage: float
    line_coverage: float
    branch_coverage: float
    function_coverage: float
    module_coverage: Dict[str, float]
    uncovered_lines: int
    total_lines: int
    critical_modules_coverage: Dict[str, float]
    coverage_trend: str  # 'improving', 'stable', 'declining'


@dataclass
class CoverageAlert:
    """Coverage alert for monitoring purposes."""
    alert_type: str  # 'regression', 'threshold', 'critical_module'
    severity: str    # 'low', 'medium', 'high', 'critical'
    message: str
    module: Optional[str] = None
    current_coverage: Optional[float] = None
    threshold: Optional[float] = None
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


class CoverageMonitor:
    """Monitors test coverage and generates reports and alerts."""
    
    def __init__(self, db_path: str = "tests/quality_assurance/coverage_history.db"):
        self.db_path = db_path
        self.coverage_thresholds = {
            'overall': 90.0,
            'critical_modules': {
                'src.services.decision_engine': 95.0,
                'src.services.validation': 95.0,
                'src.services.medical_code_validator': 95.0,
                'src.services.policy_validation': 95.0,
                'src.core.encryption': 95.0,
                'src.auth.oauth2': 90.0,
                'src.api.intake': 90.0,
                'src.api.decisions': 90.0,
            },
            'regression_threshold': 2.0,  # Alert if coverage drops by more than 2%
        }
        self.initialize_database()
    
    def initialize_database(self):
        """Initialize the coverage history database."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS coverage_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    overall_coverage REAL NOT NULL,
                    line_coverage REAL NOT NULL,
                    branch_coverage REAL NOT NULL,
                    function_coverage REAL NOT NULL,
                    uncovered_lines INTEGER NOT NULL,
                    total_lines INTEGER NOT NULL,
                    module_coverage TEXT NOT NULL,  -- JSON string
                    critical_modules_coverage TEXT NOT NULL,  -- JSON string
                    coverage_trend TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS coverage_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    module TEXT,
                    current_coverage REAL,
                    threshold REAL,
                    resolved BOOLEAN DEFAULT FALSE
                )
            """)
    
    def run_coverage_analysis(self) -> CoverageMetrics:
        """Run comprehensive coverage analysis."""
        print("Running coverage analysis...")
        
        # Run pytest with coverage
        coverage_cmd = [
            "python", "-m", "pytest", "tests/",
            "--cov=src",
            "--cov-report=xml:coverage.xml",
            "--cov-report=json:coverage.json",
            "--cov-branch",
            "--quiet"
        ]
        
        try:
            result = subprocess.run(coverage_cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                print(f"Coverage analysis failed: {result.stderr}")
                return None
        except subprocess.TimeoutExpired:
            print("Coverage analysis timed out")
            return None
        
        # Parse coverage results
        return self._parse_coverage_results()
    
    def _parse_coverage_results(self) -> CoverageMetrics:
        """Parse coverage results from generated reports."""
        # Parse JSON coverage report
        coverage_data = {}
        if os.path.exists("coverage.json"):
            with open("coverage.json", "r") as f:
                coverage_data = json.load(f)
        
        # Parse XML coverage report for additional metrics
        xml_data = {}
        if os.path.exists("coverage.xml"):
            tree = ET.parse("coverage.xml")
            root = tree.getroot()
            xml_data = self._parse_xml_coverage(root)
        
        # Calculate metrics
        overall_coverage = coverage_data.get("totals", {}).get("percent_covered", 0.0)
        line_coverage = xml_data.get("line_rate", 0.0) * 100
        branch_coverage = xml_data.get("branch_rate", 0.0) * 100
        
        # Module-level coverage
        module_coverage = {}
        critical_modules_coverage = {}
        
        for filename, file_data in coverage_data.get("files", {}).items():
            module_name = self._filename_to_module(filename)
            coverage_pct = file_data.get("summary", {}).get("percent_covered", 0.0)
            module_coverage[module_name] = coverage_pct
            
            # Check if this is a critical module
            if module_name in self.coverage_thresholds['critical_modules']:
                critical_modules_coverage[module_name] = coverage_pct
        
        # Calculate totals
        total_lines = coverage_data.get("totals", {}).get("num_statements", 0)
        covered_lines = coverage_data.get("totals", {}).get("covered_lines", 0)
        uncovered_lines = total_lines - covered_lines
        
        # Determine coverage trend
        coverage_trend = self._calculate_coverage_trend(overall_coverage)
        
        return CoverageMetrics(
            timestamp=datetime.now().isoformat(),
            overall_coverage=overall_coverage,
            line_coverage=line_coverage,
            branch_coverage=branch_coverage,
            function_coverage=xml_data.get("function_rate", 0.0) * 100,
            module_coverage=module_coverage,
            uncovered_lines=uncovered_lines,
            total_lines=total_lines,
            critical_modules_coverage=critical_modules_coverage,
            coverage_trend=coverage_trend
        )
    
    def _parse_xml_coverage(self, root) -> Dict:
        """Parse XML coverage report for additional metrics."""
        coverage_data = {}
        
        # Get overall rates
        coverage_data["line_rate"] = float(root.get("line-rate", 0))
        coverage_data["branch_rate"] = float(root.get("branch-rate", 0))
        
        # Get function coverage if available
        packages = root.find("packages")
        if packages is not None:
            total_functions = 0
            covered_functions = 0
            
            for package in packages.findall("package"):
                for class_elem in package.findall(".//class"):
                    methods = class_elem.findall("methods/method")
                    for method in methods:
                        total_functions += 1
                        if float(method.get("line-rate", 0)) > 0:
                            covered_functions += 1
            
            if total_functions > 0:
                coverage_data["function_rate"] = covered_functions / total_functions
        
        return coverage_data
    
    def _filename_to_module(self, filename: str) -> str:
        """Convert filename to module name."""
        # Remove file extension and convert path separators
        module = filename.replace(".py", "").replace("/", ".").replace("\\", ".")
        
        # Remove leading path components if present
        if module.startswith("src."):
            return module
        elif "src/" in filename:
            parts = filename.split("src/")
            if len(parts) > 1:
                return "src." + parts[1].replace("/", ".").replace(".py", "")
        
        return module
    
    def _calculate_coverage_trend(self, current_coverage: float) -> str:
        """Calculate coverage trend based on historical data."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT overall_coverage FROM coverage_history 
                ORDER BY timestamp DESC LIMIT 5
            """)
            recent_coverage = [row[0] for row in cursor.fetchall()]
        
        if len(recent_coverage) < 2:
            return "stable"
        
        # Calculate trend over last few measurements
        avg_recent = sum(recent_coverage[:3]) / min(3, len(recent_coverage))
        
        if current_coverage > avg_recent + 1.0:
            return "improving"
        elif current_coverage < avg_recent - 1.0:
            return "declining"
        else:
            return "stable"
    
    def store_coverage_metrics(self, metrics: CoverageMetrics):
        """Store coverage metrics in the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO coverage_history (
                    timestamp, overall_coverage, line_coverage, branch_coverage,
                    function_coverage, uncovered_lines, total_lines,
                    module_coverage, critical_modules_coverage, coverage_trend
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metrics.timestamp,
                metrics.overall_coverage,
                metrics.line_coverage,
                metrics.branch_coverage,
                metrics.function_coverage,
                metrics.uncovered_lines,
                metrics.total_lines,
                json.dumps(metrics.module_coverage),
                json.dumps(metrics.critical_modules_coverage),
                metrics.coverage_trend
            ))
    
    def check_coverage_alerts(self, metrics: CoverageMetrics) -> List[CoverageAlert]:
        """Check for coverage alerts based on current metrics."""
        alerts = []
        
        # Check overall coverage threshold
        if metrics.overall_coverage < self.coverage_thresholds['overall']:
            alerts.append(CoverageAlert(
                alert_type="threshold",
                severity="high",
                message=f"Overall coverage {metrics.overall_coverage:.1f}% below threshold {self.coverage_thresholds['overall']:.1f}%",
                current_coverage=metrics.overall_coverage,
                threshold=self.coverage_thresholds['overall']
            ))
        
        # Check critical module coverage
        for module, threshold in self.coverage_thresholds['critical_modules'].items():
            current = metrics.critical_modules_coverage.get(module, 0.0)
            if current < threshold:
                severity = "critical" if current < threshold - 10 else "high"
                alerts.append(CoverageAlert(
                    alert_type="critical_module",
                    severity=severity,
                    message=f"Critical module {module} coverage {current:.1f}% below threshold {threshold:.1f}%",
                    module=module,
                    current_coverage=current,
                    threshold=threshold
                ))
        
        # Check for coverage regression
        regression_alert = self._check_coverage_regression(metrics)
        if regression_alert:
            alerts.append(regression_alert)
        
        # Store alerts in database
        for alert in alerts:
            self._store_alert(alert)
        
        return alerts
    
    def _check_coverage_regression(self, metrics: CoverageMetrics) -> Optional[CoverageAlert]:
        """Check for coverage regression compared to recent history."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT overall_coverage FROM coverage_history 
                WHERE timestamp > ? 
                ORDER BY timestamp DESC LIMIT 5
            """, (
                (datetime.now() - timedelta(days=7)).isoformat(),
            ))
            recent_coverage = [row[0] for row in cursor.fetchall()]
        
        if not recent_coverage:
            return None
        
        avg_recent = sum(recent_coverage) / len(recent_coverage)
        regression = avg_recent - metrics.overall_coverage
        
        if regression > self.coverage_thresholds['regression_threshold']:
            severity = "critical" if regression > 5.0 else "high"
            return CoverageAlert(
                alert_type="regression",
                severity=severity,
                message=f"Coverage regression detected: {regression:.1f}% drop from recent average {avg_recent:.1f}%",
                current_coverage=metrics.overall_coverage,
                threshold=avg_recent
            )
        
        return None
    
    def _store_alert(self, alert: CoverageAlert):
        """Store alert in the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO coverage_alerts (
                    timestamp, alert_type, severity, message, module,
                    current_coverage, threshold
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                alert.timestamp,
                alert.alert_type,
                alert.severity,
                alert.message,
                alert.module,
                alert.current_coverage,
                alert.threshold
            ))
    
    def generate_coverage_report(self, metrics: CoverageMetrics, alerts: List[CoverageAlert]) -> str:
        """Generate comprehensive coverage report."""
        report_lines = [
            "# Test Coverage Report",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Overall Coverage Metrics",
            f"- **Overall Coverage**: {metrics.overall_coverage:.1f}%",
            f"- **Line Coverage**: {metrics.line_coverage:.1f}%",
            f"- **Branch Coverage**: {metrics.branch_coverage:.1f}%",
            f"- **Function Coverage**: {metrics.function_coverage:.1f}%",
            f"- **Coverage Trend**: {metrics.coverage_trend.title()}",
            "",
            f"## Coverage Statistics",
            f"- **Total Lines**: {metrics.total_lines:,}",
            f"- **Covered Lines**: {metrics.total_lines - metrics.uncovered_lines:,}",
            f"- **Uncovered Lines**: {metrics.uncovered_lines:,}",
            "",
        ]
        
        # Critical modules section
        if metrics.critical_modules_coverage:
            report_lines.extend([
                "## Critical Module Coverage",
                ""
            ])
            
            for module, coverage in sorted(metrics.critical_modules_coverage.items()):
                threshold = self.coverage_thresholds['critical_modules'].get(module, 90.0)
                status = "✅" if coverage >= threshold else "❌"
                report_lines.append(f"- {status} **{module}**: {coverage:.1f}% (threshold: {threshold:.1f}%)")
            
            report_lines.append("")
        
        # Low coverage modules
        low_coverage_modules = {
            module: coverage for module, coverage in metrics.module_coverage.items()
            if coverage < 80.0
        }
        
        if low_coverage_modules:
            report_lines.extend([
                "## Modules with Low Coverage (< 80%)",
                ""
            ])
            
            for module, coverage in sorted(low_coverage_modules.items(), key=lambda x: x[1]):
                report_lines.append(f"- **{module}**: {coverage:.1f}%")
            
            report_lines.append("")
        
        # Alerts section
        if alerts:
            report_lines.extend([
                "## Coverage Alerts",
                ""
            ])
            
            for alert in sorted(alerts, key=lambda x: x.severity, reverse=True):
                severity_icon = {
                    'critical': '🚨',
                    'high': '⚠️',
                    'medium': '⚡',
                    'low': 'ℹ️'
                }.get(alert.severity, 'ℹ️')
                
                report_lines.append(f"- {severity_icon} **{alert.severity.upper()}**: {alert.message}")
            
            report_lines.append("")
        
        # Recommendations
        report_lines.extend([
            "## Recommendations",
            ""
        ])
        
        if metrics.overall_coverage < self.coverage_thresholds['overall']:
            report_lines.append(f"- 🎯 Increase overall coverage to meet {self.coverage_thresholds['overall']:.1f}% threshold")
        
        if low_coverage_modules:
            report_lines.append("- 📈 Focus on improving coverage for modules below 80%")
        
        if any(alert.alert_type == "regression" for alert in alerts):
            report_lines.append("- 🔍 Investigate recent changes that may have caused coverage regression")
        
        if any(alert.alert_type == "critical_module" for alert in alerts):
            report_lines.append("- 🚨 Prioritize improving coverage for critical business logic modules")
        
        if metrics.coverage_trend == "declining":
            report_lines.append("- 📉 Address declining coverage trend with targeted test improvements")
        
        if not alerts and metrics.overall_coverage >= self.coverage_thresholds['overall']:
            report_lines.append("- ✅ Coverage metrics are healthy - maintain current testing practices")
        
        return "\n".join(report_lines)
    
    def get_coverage_history(self, days: int = 30) -> List[CoverageMetrics]:
        """Get coverage history for the specified number of days."""
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT * FROM coverage_history 
                WHERE timestamp > ? 
                ORDER BY timestamp DESC
            """, (cutoff_date,))
            
            history = []
            for row in cursor.fetchall():
                metrics = CoverageMetrics(
                    timestamp=row[1],
                    overall_coverage=row[2],
                    line_coverage=row[3],
                    branch_coverage=row[4],
                    function_coverage=row[5],
                    uncovered_lines=row[6],
                    total_lines=row[7],
                    module_coverage=json.loads(row[8]),
                    critical_modules_coverage=json.loads(row[9]),
                    coverage_trend=row[10]
                )
                history.append(metrics)
            
            return history
    
    def get_active_alerts(self) -> List[CoverageAlert]:
        """Get all active (unresolved) coverage alerts."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT * FROM coverage_alerts 
                WHERE resolved = FALSE 
                ORDER BY timestamp DESC
            """)
            
            alerts = []
            for row in cursor.fetchall():
                alert = CoverageAlert(
                    alert_type=row[2],
                    severity=row[3],
                    message=row[4],
                    module=row[5],
                    current_coverage=row[6],
                    threshold=row[7],
                    timestamp=row[1]
                )
                alerts.append(alert)
            
            return alerts
    
    def resolve_alert(self, alert_id: int):
        """Mark an alert as resolved."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE coverage_alerts 
                SET resolved = TRUE 
                WHERE id = ?
            """, (alert_id,))
    
    def run_monitoring_cycle(self) -> Tuple[CoverageMetrics, List[CoverageAlert], str]:
        """Run a complete monitoring cycle."""
        print("Starting coverage monitoring cycle...")
        
        # Run coverage analysis
        metrics = self.run_coverage_analysis()
        if not metrics:
            return None, [], "Coverage analysis failed"
        
        # Store metrics
        self.store_coverage_metrics(metrics)
        
        # Check for alerts
        alerts = self.check_coverage_alerts(metrics)
        
        # Generate report
        report = self.generate_coverage_report(metrics, alerts)
        
        # Save report to file
        report_path = f"tests/quality_assurance/coverage_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w") as f:
            f.write(report)
        
        print(f"Coverage monitoring complete. Report saved to {report_path}")
        
        return metrics, alerts, report


def main():
    """Main function for running coverage monitoring."""
    monitor = CoverageMonitor()
    
    # Run monitoring cycle
    metrics, alerts, report = monitor.run_monitoring_cycle()
    
    if metrics:
        print(f"\nCoverage Summary:")
        print(f"Overall Coverage: {metrics.overall_coverage:.1f}%")
        print(f"Coverage Trend: {metrics.coverage_trend}")
        
        if alerts:
            print(f"\nAlerts Generated: {len(alerts)}")
            for alert in alerts:
                print(f"- {alert.severity.upper()}: {alert.message}")
        else:
            print("\nNo coverage alerts generated.")
    
    return 0 if not alerts or all(alert.severity in ['low', 'medium'] for alert in alerts) else 1


if __name__ == "__main__":
    exit(main())