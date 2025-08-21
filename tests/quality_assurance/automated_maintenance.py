#!/usr/bin/env python3
"""
Automated test maintenance system for the Prior Authorization System test suite.

This module provides automated maintenance tasks including test health monitoring,
performance optimization, documentation updates, and quality assurance procedures.
"""

import os
import json
import sqlite3
import subprocess
import schedule
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import logging

from coverage_monitor import CoverageMonitor
from test_quality_metrics import TestQualityAnalyzer


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('tests/quality_assurance/maintenance.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class MaintenanceTask:
    """Represents a maintenance task."""
    name: str
    description: str
    frequency: str  # 'daily', 'weekly', 'monthly'
    last_run: Optional[str] = None
    status: str = 'pending'  # 'pending', 'running', 'completed', 'failed'
    duration: Optional[float] = None
    error_message: Optional[str] = None


class AutomatedTestMaintenance:
    """Automated test maintenance system."""
    
    def __init__(self):
        self.db_path = "tests/quality_assurance/maintenance_history.db"
        self.coverage_monitor = CoverageMonitor()
        self.quality_analyzer = TestQualityAnalyzer()
        self.maintenance_config = self._load_maintenance_config()
        self.initialize_database()
        
    def _load_maintenance_config(self) -> Dict:
        """Load maintenance configuration."""
        return {
            'coverage_thresholds': {
                'overall': 90.0,
                'critical_modules': 95.0,
                'regression_alert': 2.0
            },
            'quality_thresholds': {
                'overall_quality': 80.0,
                'documentation': 90.0,
                'performance': 85.0,
                'compliance': 100.0
            },
            'performance_limits': {
                'max_test_time': 30.0,
                'max_suite_time': 600.0,
                'max_slow_tests': 10
            },
            'notification_settings': {
                'email_alerts': True,
                'slack_notifications': False,
                'alert_threshold': 'medium'
            }
        }
    
    def initialize_database(self):
        """Initialize maintenance history database."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS maintenance_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    frequency TEXT NOT NULL,
                    last_run TEXT,
                    status TEXT NOT NULL,
                    duration REAL,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS maintenance_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    report_data TEXT NOT NULL,  -- JSON
                    summary TEXT NOT NULL,
                    alerts_count INTEGER DEFAULT 0,
                    recommendations_count INTEGER DEFAULT 0
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS maintenance_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    resolved BOOLEAN DEFAULT FALSE,
                    resolution_notes TEXT
                )
            """)
    
    def register_maintenance_tasks(self):
        """Register all maintenance tasks with the scheduler."""
        logger.info("Registering maintenance tasks...")
        
        # Daily tasks
        schedule.every().day.at("02:00").do(self.run_daily_health_check)
        schedule.every().day.at("03:00").do(self.run_coverage_monitoring)
        schedule.every().day.at("04:00").do(self.run_phi_compliance_check)
        
        # Weekly tasks
        schedule.every().monday.at("01:00").do(self.run_weekly_quality_analysis)
        schedule.every().tuesday.at("01:00").do(self.run_performance_analysis)
        schedule.every().wednesday.at("01:00").do(self.run_documentation_check)
        
        # Monthly tasks
        schedule.every().month.do(self.run_comprehensive_maintenance)
        
        logger.info("Maintenance tasks registered successfully")
    
    def run_daily_health_check(self):
        """Run daily test suite health check."""
        task = MaintenanceTask(
            name="daily_health_check",
            description="Daily test suite health and reliability check",
            frequency="daily"
        )
        
        return self._execute_task(task, self._daily_health_check_impl)
    
    def _daily_health_check_impl(self) -> Dict:
        """Implementation of daily health check."""
        logger.info("Running daily health check...")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'test_execution': {},
            'database_health': {},
            'dependency_check': {},
            'issues': [],
            'recommendations': []
        }
        
        # Test execution health
        try:
            cmd = ["python", "-m", "pytest", "tests/", "--collect-only", "-q"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                # Count collected tests
                output_lines = result.stdout.split('\n')
                test_count = sum(1 for line in output_lines if 'collected' in line)
                results['test_execution']['status'] = 'healthy'
                results['test_execution']['collected_tests'] = test_count
            else:
                results['test_execution']['status'] = 'unhealthy'
                results['test_execution']['error'] = result.stderr
                results['issues'].append("Test collection failed")
                
        except subprocess.TimeoutExpired:
            results['test_execution']['status'] = 'timeout'
            results['issues'].append("Test collection timed out")
        
        # Database connectivity check
        try:
            from src.database.connection import get_session
            with get_session() as session:
                session.execute("SELECT 1")
            results['database_health']['status'] = 'healthy'
        except Exception as e:
            results['database_health']['status'] = 'unhealthy'
            results['database_health']['error'] = str(e)
            results['issues'].append("Database connectivity issues")
        
        # Dependency check
        try:
            import pytest
            import coverage
            import pydantic
            results['dependency_check']['status'] = 'healthy'
            results['dependency_check']['versions'] = {
                'pytest': pytest.__version__,
                'coverage': coverage.__version__,
                'pydantic': pydantic.__version__
            }
        except ImportError as e:
            results['dependency_check']['status'] = 'unhealthy'
            results['dependency_check']['error'] = str(e)
            results['issues'].append("Missing critical dependencies")
        
        # Generate recommendations
        if results['issues']:
            results['recommendations'].append("Address identified issues immediately")
        else:
            results['recommendations'].append("Test suite health is good")
        
        return results
    
    def run_coverage_monitoring(self):
        """Run coverage monitoring and analysis."""
        task = MaintenanceTask(
            name="coverage_monitoring",
            description="Monitor test coverage and generate alerts",
            frequency="daily"
        )
        
        return self._execute_task(task, self._coverage_monitoring_impl)
    
    def _coverage_monitoring_impl(self) -> Dict:
        """Implementation of coverage monitoring."""
        logger.info("Running coverage monitoring...")
        
        # Run coverage analysis
        metrics, alerts, report = self.coverage_monitor.run_monitoring_cycle()
        
        if not metrics:
            return {
                'status': 'failed',
                'error': 'Coverage analysis failed',
                'timestamp': datetime.now().isoformat()
            }
        
        # Store alerts
        for alert in alerts:
            self._store_maintenance_alert(
                alert_type="coverage",
                severity=alert.severity,
                message=alert.message
            )
        
        return {
            'status': 'completed',
            'timestamp': datetime.now().isoformat(),
            'overall_coverage': metrics.overall_coverage,
            'coverage_trend': metrics.coverage_trend,
            'alerts_generated': len(alerts),
            'critical_alerts': len([a for a in alerts if a.severity == 'critical']),
            'report_path': f"coverage_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        }
    
    def run_phi_compliance_check(self):
        """Run PHI compliance validation."""
        task = MaintenanceTask(
            name="phi_compliance_check",
            description="Validate PHI compliance across test suite",
            frequency="daily"
        )
        
        return self._execute_task(task, self._phi_compliance_check_impl)
    
    def _phi_compliance_check_impl(self) -> Dict:
        """Implementation of PHI compliance check."""
        logger.info("Running PHI compliance check...")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'compliance_status': 'compliant',
            'violations': [],
            'files_scanned': 0,
            'issues': []
        }
        
        try:
            # Run PHI compliance validation
            cmd = ["python", "validate_phi_compliance.py", "--comprehensive"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                results['compliance_status'] = 'compliant'
                # Parse output for file count
                output_lines = result.stdout.split('\n')
                for line in output_lines:
                    if 'files scanned' in line.lower():
                        try:
                            results['files_scanned'] = int(line.split()[0])
                        except (ValueError, IndexError):
                            pass
            else:
                results['compliance_status'] = 'violations_found'
                results['violations'] = result.stderr.split('\n')
                results['issues'].append("PHI compliance violations detected")
                
                # Store critical alert
                self._store_maintenance_alert(
                    alert_type="phi_compliance",
                    severity="critical",
                    message="PHI compliance violations detected in test suite"
                )
                
        except subprocess.TimeoutExpired:
            results['compliance_status'] = 'check_timeout'
            results['issues'].append("PHI compliance check timed out")
        except Exception as e:
            results['compliance_status'] = 'check_failed'
            results['issues'].append(f"PHI compliance check failed: {str(e)}")
        
        return results
    
    def run_weekly_quality_analysis(self):
        """Run weekly test quality analysis."""
        task = MaintenanceTask(
            name="weekly_quality_analysis",
            description="Comprehensive test quality analysis and reporting",
            frequency="weekly"
        )
        
        return self._execute_task(task, self._weekly_quality_analysis_impl)
    
    def _weekly_quality_analysis_impl(self) -> Dict:
        """Implementation of weekly quality analysis."""
        logger.info("Running weekly quality analysis...")
        
        # Run quality analysis
        metrics = self.quality_analyzer.analyze_test_suite_quality()
        
        # Generate quality report
        report = self.quality_analyzer.generate_quality_report(metrics)
        
        # Save report
        report_path = f"tests/quality_assurance/weekly_quality_report_{datetime.now().strftime('%Y%m%d')}.md"
        with open(report_path, "w") as f:
            f.write(report)
        
        # Check for quality alerts
        alerts = []
        if metrics.overall_quality_score < self.maintenance_config['quality_thresholds']['overall_quality']:
            alerts.append({
                'type': 'quality_threshold',
                'severity': 'high',
                'message': f"Overall quality score {metrics.overall_quality_score:.1f} below threshold"
            })
        
        if metrics.documentation_quality_score < self.maintenance_config['quality_thresholds']['documentation']:
            alerts.append({
                'type': 'documentation_quality',
                'severity': 'medium',
                'message': f"Documentation quality {metrics.documentation_quality_score:.1f} below threshold"
            })
        
        # Store alerts
        for alert in alerts:
            self._store_maintenance_alert(
                alert_type=alert['type'],
                severity=alert['severity'],
                message=alert['message']
            )
        
        return {
            'status': 'completed',
            'timestamp': datetime.now().isoformat(),
            'overall_quality_score': metrics.overall_quality_score,
            'total_tests': metrics.total_tests,
            'alerts_generated': len(alerts),
            'report_path': report_path,
            'recommendations': metrics.recommendations[:5]  # Top 5 recommendations
        }
    
    def run_performance_analysis(self):
        """Run performance analysis and optimization."""
        task = MaintenanceTask(
            name="performance_analysis",
            description="Analyze test performance and identify optimization opportunities",
            frequency="weekly"
        )
        
        return self._execute_task(task, self._performance_analysis_impl)
    
    def _performance_analysis_impl(self) -> Dict:
        """Implementation of performance analysis."""
        logger.info("Running performance analysis...")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'slow_tests': [],
            'performance_issues': [],
            'recommendations': []
        }
        
        try:
            # Run tests with timing analysis
            cmd = [
                "python", "-m", "pytest", "tests/",
                "--durations=20",
                "--tb=no",
                "-q"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode == 0:
                # Parse slow tests from output
                output_lines = result.stdout.split('\n')
                for line in output_lines:
                    if 's call' in line or 's setup' in line or 's teardown' in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            try:
                                duration = float(parts[0].replace('s', ''))
                                if duration > self.maintenance_config['performance_limits']['max_test_time']:
                                    test_name = parts[-1] if len(parts) > 2 else 'unknown'
                                    results['slow_tests'].append({
                                        'test_name': test_name,
                                        'duration': duration
                                    })
                            except ValueError:
                                continue
                
                # Generate performance recommendations
                if len(results['slow_tests']) > self.maintenance_config['performance_limits']['max_slow_tests']:
                    results['performance_issues'].append("Too many slow tests detected")
                    results['recommendations'].append("Optimize slow tests or mark them with @pytest.mark.slow")
                
                if not results['performance_issues']:
                    results['recommendations'].append("Test performance is within acceptable limits")
                    
            else:
                results['performance_issues'].append("Performance analysis failed to complete")
                
        except subprocess.TimeoutExpired:
            results['performance_issues'].append("Performance analysis timed out")
            results['recommendations'].append("Investigate test suite performance issues")
        
        return results
    
    def run_documentation_check(self):
        """Run documentation quality check."""
        task = MaintenanceTask(
            name="documentation_check",
            description="Check and improve test documentation quality",
            frequency="weekly"
        )
        
        return self._execute_task(task, self._documentation_check_impl)
    
    def _documentation_check_impl(self) -> Dict:
        """Implementation of documentation check."""
        logger.info("Running documentation check...")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'files_checked': 0,
            'undocumented_methods': 0,
            'poor_documentation': 0,
            'improvements_made': 0,
            'recommendations': []
        }
        
        try:
            # Run documentation improvement script
            cmd = ["python", "tests/improve_test_documentation.py"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                # Parse output for statistics
                output_lines = result.stdout.split('\n')
                for line in output_lines:
                    if 'Improved' in line and 'files' in line:
                        try:
                            parts = line.split()
                            results['improvements_made'] = int(parts[1])
                        except (ValueError, IndexError):
                            pass
                
                if results['improvements_made'] > 0:
                    results['recommendations'].append(f"Review {results['improvements_made']} improved documentation files")
                else:
                    results['recommendations'].append("Documentation quality is satisfactory")
                    
            else:
                results['recommendations'].append("Documentation check encountered issues")
                
        except subprocess.TimeoutExpired:
            results['recommendations'].append("Documentation check timed out")
        except Exception as e:
            results['recommendations'].append(f"Documentation check failed: {str(e)}")
        
        return results
    
    def run_comprehensive_maintenance(self):
        """Run comprehensive monthly maintenance."""
        task = MaintenanceTask(
            name="comprehensive_maintenance",
            description="Comprehensive monthly maintenance and optimization",
            frequency="monthly"
        )
        
        return self._execute_task(task, self._comprehensive_maintenance_impl)
    
    def _comprehensive_maintenance_impl(self) -> Dict:
        """Implementation of comprehensive maintenance."""
        logger.info("Running comprehensive maintenance...")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'tasks_completed': [],
            'issues_found': [],
            'optimizations_applied': [],
            'recommendations': []
        }
        
        # Run all maintenance tasks
        maintenance_tasks = [
            ('health_check', self._daily_health_check_impl),
            ('coverage_analysis', self._coverage_monitoring_impl),
            ('quality_analysis', self._weekly_quality_analysis_impl),
            ('performance_analysis', self._performance_analysis_impl),
            ('documentation_check', self._documentation_check_impl)
        ]
        
        for task_name, task_impl in maintenance_tasks:
            try:
                task_result = task_impl()
                results['tasks_completed'].append(task_name)
                
                # Collect issues and recommendations
                if 'issues' in task_result:
                    results['issues_found'].extend(task_result['issues'])
                if 'recommendations' in task_result:
                    results['recommendations'].extend(task_result['recommendations'])
                    
            except Exception as e:
                logger.error(f"Comprehensive maintenance task {task_name} failed: {e}")
                results['issues_found'].append(f"Task {task_name} failed: {str(e)}")
        
        # Generate comprehensive report
        report_path = f"tests/quality_assurance/comprehensive_maintenance_report_{datetime.now().strftime('%Y%m%d')}.md"
        self._generate_comprehensive_report(results, report_path)
        
        return results
    
    def _execute_task(self, task: MaintenanceTask, task_impl) -> Dict:
        """Execute a maintenance task with error handling and logging."""
        start_time = time.time()
        task.status = 'running'
        
        try:
            logger.info(f"Starting task: {task.name}")
            result = task_impl()
            
            task.status = 'completed'
            task.duration = time.time() - start_time
            task.last_run = datetime.now().isoformat()
            
            logger.info(f"Task {task.name} completed successfully in {task.duration:.2f}s")
            
            # Store task execution record
            self._store_task_execution(task, result)
            
            return result
            
        except Exception as e:
            task.status = 'failed'
            task.duration = time.time() - start_time
            task.error_message = str(e)
            task.last_run = datetime.now().isoformat()
            
            logger.error(f"Task {task.name} failed after {task.duration:.2f}s: {e}")
            
            # Store failure record
            self._store_task_execution(task, {'error': str(e)})
            
            # Generate alert for failed task
            self._store_maintenance_alert(
                alert_type="task_failure",
                severity="high",
                message=f"Maintenance task {task.name} failed: {str(e)}"
            )
            
            return {'status': 'failed', 'error': str(e)}
    
    def _store_task_execution(self, task: MaintenanceTask, result: Dict):
        """Store task execution record in database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO maintenance_tasks (
                    task_name, description, frequency, last_run, status,
                    duration, error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.name,
                task.description,
                task.frequency,
                task.last_run,
                task.status,
                task.duration,
                task.error_message,
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ))
            
            # Store detailed results
            conn.execute("""
                INSERT INTO maintenance_reports (
                    report_type, timestamp, report_data, summary,
                    alerts_count, recommendations_count
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                task.name,
                datetime.now().isoformat(),
                json.dumps(result),
                f"Task {task.name} {task.status}",
                len(result.get('alerts', [])),
                len(result.get('recommendations', []))
            ))
    
    def _store_maintenance_alert(self, alert_type: str, severity: str, message: str):
        """Store maintenance alert in database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO maintenance_alerts (
                    alert_type, severity, message, timestamp
                ) VALUES (?, ?, ?, ?)
            """, (
                alert_type,
                severity,
                message,
                datetime.now().isoformat()
            ))
    
    def _generate_comprehensive_report(self, results: Dict, report_path: str):
        """Generate comprehensive maintenance report."""
        report_lines = [
            "# Comprehensive Test Suite Maintenance Report",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Executive Summary",
            f"- **Tasks Completed**: {len(results['tasks_completed'])}",
            f"- **Issues Found**: {len(results['issues_found'])}",
            f"- **Optimizations Applied**: {len(results['optimizations_applied'])}",
            f"- **Recommendations Generated**: {len(results['recommendations'])}",
            "",
        ]
        
        if results['tasks_completed']:
            report_lines.extend([
                "## Completed Tasks",
                ""
            ])
            for task in results['tasks_completed']:
                report_lines.append(f"- ✅ {task}")
            report_lines.append("")
        
        if results['issues_found']:
            report_lines.extend([
                "## Issues Identified",
                ""
            ])
            for issue in results['issues_found']:
                report_lines.append(f"- ⚠️ {issue}")
            report_lines.append("")
        
        if results['recommendations']:
            report_lines.extend([
                "## Recommendations",
                ""
            ])
            for i, rec in enumerate(results['recommendations'], 1):
                report_lines.append(f"{i}. {rec}")
            report_lines.append("")
        
        # Write report
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w") as f:
            f.write("\n".join(report_lines))
        
        logger.info(f"Comprehensive maintenance report saved to {report_path}")
    
    def run_scheduler(self):
        """Run the maintenance scheduler."""
        logger.info("Starting automated test maintenance scheduler...")
        
        self.register_maintenance_tasks()
        
        while True:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except KeyboardInterrupt:
                logger.info("Maintenance scheduler stopped by user")
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                time.sleep(300)  # Wait 5 minutes before retrying
    
    def run_single_task(self, task_name: str) -> Dict:
        """Run a single maintenance task on demand."""
        task_map = {
            'health_check': self.run_daily_health_check,
            'coverage_monitoring': self.run_coverage_monitoring,
            'phi_compliance': self.run_phi_compliance_check,
            'quality_analysis': self.run_weekly_quality_analysis,
            'performance_analysis': self.run_performance_analysis,
            'documentation_check': self.run_documentation_check,
            'comprehensive': self.run_comprehensive_maintenance
        }
        
        if task_name not in task_map:
            return {'status': 'failed', 'error': f'Unknown task: {task_name}'}
        
        return task_map[task_name]()


def main():
    """Main function for running automated maintenance."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Automated Test Maintenance System")
    parser.add_argument('--task', help='Run specific task', choices=[
        'health_check', 'coverage_monitoring', 'phi_compliance',
        'quality_analysis', 'performance_analysis', 'documentation_check',
        'comprehensive'
    ])
    parser.add_argument('--scheduler', action='store_true', help='Run maintenance scheduler')
    
    args = parser.parse_args()
    
    maintenance = AutomatedTestMaintenance()
    
    if args.scheduler:
        maintenance.run_scheduler()
    elif args.task:
        result = maintenance.run_single_task(args.task)
        print(f"Task {args.task} completed with status: {result.get('status', 'unknown')}")
        if result.get('error'):
            print(f"Error: {result['error']}")
        return 0 if result.get('status') == 'completed' else 1
    else:
        # Run comprehensive maintenance by default
        result = maintenance.run_comprehensive_maintenance()
        print(f"Comprehensive maintenance completed")
        return 0


if __name__ == "__main__":
    exit(main())