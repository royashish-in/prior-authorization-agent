"""
Test execution monitoring and performance analysis.

This module provides comprehensive monitoring of test execution,
including performance metrics, reliability tracking, and regression detection.
"""

import json
import time
import threading
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import pytest
import psutil
import os


@dataclass
class TestExecutionMetrics:
    """Metrics for a single test execution."""
    test_name: str
    duration: float
    status: str  # passed, failed, skipped, error
    memory_usage_mb: float
    cpu_usage_percent: float
    timestamp: float
    error_message: Optional[str] = None
    warnings: List[str] = None
    markers: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
        if self.markers is None:
            self.markers = []


@dataclass
class TestSuiteMetrics:
    """Metrics for an entire test suite execution."""
    suite_name: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    skipped_tests: int
    error_tests: int
    total_duration: float
    average_duration: float
    memory_peak_mb: float
    cpu_average_percent: float
    timestamp: float
    slow_tests: List[Tuple[str, float]]
    failed_test_details: List[Dict[str, Any]]


class TestPerformanceMonitor:
    """Monitor test performance and collect metrics."""
    
    def __init__(self, history_size: int = 1000):
        self.history_size = history_size
        self.test_metrics = deque(maxlen=history_size)
        self.suite_metrics = deque(maxlen=100)  # Keep last 100 suite runs
        self.performance_baselines = {}
        self.slow_test_threshold = 5.0  # seconds
        self.memory_threshold = 100.0  # MB
        self.reliability_window = 50  # tests to consider for reliability
        self._lock = threading.Lock()
        
        # Performance tracking
        self.test_durations = defaultdict(list)
        self.test_reliability = defaultdict(list)  # True for pass, False for fail
        self.memory_usage_history = defaultdict(list)
        
        # Regression detection
        self.performance_regression_threshold = 1.5  # 50% slower
        self.reliability_regression_threshold = 0.8  # 80% pass rate
    
    def record_test_execution(self, test_name: str, duration: float, status: str,
                            memory_usage: float = 0.0, cpu_usage: float = 0.0,
                            error_message: str = None, warnings: List[str] = None,
                            markers: List[str] = None):
        """Record metrics for a single test execution."""
        with self._lock:
            metrics = TestExecutionMetrics(
                test_name=test_name,
                duration=duration,
                status=status,
                memory_usage_mb=memory_usage,
                cpu_usage_percent=cpu_usage,
                timestamp=time.time(),
                error_message=error_message,
                warnings=warnings or [],
                markers=markers or []
            )
            
            self.test_metrics.append(metrics)
            
            # Update performance tracking
            self.test_durations[test_name].append(duration)
            if len(self.test_durations[test_name]) > self.history_size:
                self.test_durations[test_name].pop(0)
            
            # Update reliability tracking
            self.test_reliability[test_name].append(status == "passed")
            if len(self.test_reliability[test_name]) > self.reliability_window:
                self.test_reliability[test_name].pop(0)
            
            # Update memory usage tracking
            if memory_usage > 0:
                self.memory_usage_history[test_name].append(memory_usage)
                if len(self.memory_usage_history[test_name]) > self.history_size:
                    self.memory_usage_history[test_name].pop(0)
    
    def record_suite_execution(self, suite_name: str, test_results: List[TestExecutionMetrics]):
        """Record metrics for an entire test suite execution."""
        with self._lock:
            if not test_results:
                return
            
            total_tests = len(test_results)
            passed_tests = sum(1 for t in test_results if t.status == "passed")
            failed_tests = sum(1 for t in test_results if t.status == "failed")
            skipped_tests = sum(1 for t in test_results if t.status == "skipped")
            error_tests = sum(1 for t in test_results if t.status == "error")
            
            total_duration = sum(t.duration for t in test_results)
            average_duration = total_duration / total_tests if total_tests > 0 else 0
            
            memory_peak = max((t.memory_usage_mb for t in test_results), default=0)
            cpu_average = statistics.mean([t.cpu_usage_percent for t in test_results if t.cpu_usage_percent > 0]) if any(t.cpu_usage_percent > 0 for t in test_results) else 0
            
            # Identify slow tests
            slow_tests = [(t.test_name, t.duration) for t in test_results 
                         if t.duration > self.slow_test_threshold]
            slow_tests.sort(key=lambda x: x[1], reverse=True)
            
            # Collect failed test details
            failed_test_details = [
                {
                    "test_name": t.test_name,
                    "duration": t.duration,
                    "error_message": t.error_message,
                    "warnings": t.warnings
                }
                for t in test_results if t.status in ["failed", "error"]
            ]
            
            suite_metrics = TestSuiteMetrics(
                suite_name=suite_name,
                total_tests=total_tests,
                passed_tests=passed_tests,
                failed_tests=failed_tests,
                skipped_tests=skipped_tests,
                error_tests=error_tests,
                total_duration=total_duration,
                average_duration=average_duration,
                memory_peak_mb=memory_peak,
                cpu_average_percent=cpu_average,
                timestamp=time.time(),
                slow_tests=slow_tests[:10],  # Top 10 slowest
                failed_test_details=failed_test_details
            )
            
            self.suite_metrics.append(suite_metrics)
    
    def identify_slow_tests(self, threshold: float = None) -> List[Tuple[str, float, float]]:
        """Identify consistently slow tests."""
        threshold = threshold or self.slow_test_threshold
        slow_tests = []
        
        with self._lock:
            for test_name, durations in self.test_durations.items():
                if len(durations) >= 3:  # Need at least 3 runs
                    avg_duration = statistics.mean(durations)
                    if avg_duration > threshold:
                        median_duration = statistics.median(durations)
                        slow_tests.append((test_name, avg_duration, median_duration))
        
        return sorted(slow_tests, key=lambda x: x[1], reverse=True)
    
    def identify_unreliable_tests(self, min_runs: int = 5) -> List[Tuple[str, float, int, int]]:
        """Identify tests with poor reliability (frequent failures)."""
        unreliable_tests = []
        
        with self._lock:
            for test_name, results in self.test_reliability.items():
                if len(results) >= min_runs:
                    pass_rate = sum(results) / len(results)
                    if pass_rate < self.reliability_regression_threshold:
                        total_runs = len(results)
                        failed_runs = total_runs - sum(results)
                        unreliable_tests.append((test_name, pass_rate, total_runs, failed_runs))
        
        return sorted(unreliable_tests, key=lambda x: x[1])  # Sort by pass rate (lowest first)
    
    def detect_performance_regressions(self, window_size: int = 10) -> List[Dict[str, Any]]:
        """Detect performance regressions in test execution."""
        regressions = []
        
        with self._lock:
            for test_name, durations in self.test_durations.items():
                if len(durations) >= window_size * 2:  # Need enough data
                    # Compare recent performance to historical baseline
                    recent_durations = durations[-window_size:]
                    historical_durations = durations[:-window_size]
                    
                    recent_avg = statistics.mean(recent_durations)
                    historical_avg = statistics.mean(historical_durations)
                    
                    if recent_avg > historical_avg * self.performance_regression_threshold:
                        regression_factor = recent_avg / historical_avg
                        regressions.append({
                            "test_name": test_name,
                            "regression_factor": regression_factor,
                            "recent_avg_duration": recent_avg,
                            "historical_avg_duration": historical_avg,
                            "recent_runs": len(recent_durations),
                            "historical_runs": len(historical_durations)
                        })
        
        return sorted(regressions, key=lambda x: x["regression_factor"], reverse=True)
    
    def get_test_reliability_report(self) -> Dict[str, Any]:
        """Generate a comprehensive test reliability report."""
        with self._lock:
            total_test_executions = len(self.test_metrics)
            if total_test_executions == 0:
                return {"error": "No test executions recorded"}
            
            # Overall statistics
            status_counts = defaultdict(int)
            total_duration = 0
            memory_usage_values = []
            
            for metrics in self.test_metrics:
                status_counts[metrics.status] += 1
                total_duration += metrics.duration
                if metrics.memory_usage_mb > 0:
                    memory_usage_values.append(metrics.memory_usage_mb)
            
            overall_pass_rate = status_counts["passed"] / total_test_executions
            average_duration = total_duration / total_test_executions
            
            # Memory statistics
            memory_stats = {}
            if memory_usage_values:
                memory_stats = {
                    "average_mb": statistics.mean(memory_usage_values),
                    "median_mb": statistics.median(memory_usage_values),
                    "max_mb": max(memory_usage_values),
                    "min_mb": min(memory_usage_values)
                }
            
            # Identify problem areas
            slow_tests = self.identify_slow_tests()
            unreliable_tests = self.identify_unreliable_tests()
            regressions = self.detect_performance_regressions()
            
            return {
                "summary": {
                    "total_executions": total_test_executions,
                    "overall_pass_rate": round(overall_pass_rate, 3),
                    "average_duration": round(average_duration, 3),
                    "status_distribution": dict(status_counts),
                    "memory_usage": memory_stats
                },
                "slow_tests": slow_tests[:10],
                "unreliable_tests": unreliable_tests[:10],
                "performance_regressions": regressions[:10],
                "recommendations": self._generate_recommendations(
                    slow_tests, unreliable_tests, regressions, overall_pass_rate
                )
            }
    
    def _generate_recommendations(self, slow_tests: List, unreliable_tests: List, 
                                regressions: List, pass_rate: float) -> List[str]:
        """Generate recommendations based on test metrics."""
        recommendations = []
        
        if len(slow_tests) > 0:
            recommendations.append(f"Optimize {len(slow_tests)} slow tests (>{self.slow_test_threshold}s)")
        
        if len(unreliable_tests) > 0:
            recommendations.append(f"Fix {len(unreliable_tests)} unreliable tests (<{self.reliability_regression_threshold*100}% pass rate)")
        
        if len(regressions) > 0:
            recommendations.append(f"Investigate {len(regressions)} performance regressions")
        
        if pass_rate < 0.95:
            recommendations.append(f"Overall pass rate is {pass_rate:.1%}, target is >95%")
        
        return recommendations
    
    def export_metrics(self, filepath: str):
        """Export metrics to a JSON file."""
        with self._lock:
            data = {
                "test_metrics": [asdict(m) for m in self.test_metrics],
                "suite_metrics": [asdict(m) for m in self.suite_metrics],
                "export_timestamp": time.time(),
                "export_date": datetime.now(timezone.utc).isoformat()
            }
        
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    def import_metrics(self, filepath: str):
        """Import metrics from a JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        with self._lock:
            # Import test metrics
            for metric_data in data.get("test_metrics", []):
                metrics = TestExecutionMetrics(**metric_data)
                self.test_metrics.append(metrics)
                
                # Update tracking dictionaries
                test_name = metrics.test_name
                self.test_durations[test_name].append(metrics.duration)
                self.test_reliability[test_name].append(metrics.status == "passed")
                if metrics.memory_usage_mb > 0:
                    self.memory_usage_history[test_name].append(metrics.memory_usage_mb)
            
            # Import suite metrics
            for suite_data in data.get("suite_metrics", []):
                suite_metrics = TestSuiteMetrics(**suite_data)
                self.suite_metrics.append(suite_metrics)


class TestExecutionTracker:
    """Track test execution in real-time during pytest runs."""
    
    def __init__(self, monitor: TestPerformanceMonitor):
        self.monitor = monitor
        self.current_test_start = None
        self.current_test_name = None
        self.process = psutil.Process()
        self.initial_memory = self.process.memory_info().rss / 1024 / 1024  # MB
    
    def pytest_runtest_setup(self, item):
        """Called before each test setup."""
        self.current_test_name = item.nodeid
        self.current_test_start = time.time()
    
    def pytest_runtest_call(self, item):
        """Called during test execution."""
        # Update start time for more accurate measurement
        self.current_test_start = time.time()
    
    def pytest_runtest_teardown(self, item, nextitem):
        """Called after each test teardown."""
        if self.current_test_start and self.current_test_name:
            duration = time.time() - self.current_test_start
            
            # Get current memory usage
            current_memory = self.process.memory_info().rss / 1024 / 1024  # MB
            memory_usage = current_memory - self.initial_memory
            
            # Get CPU usage (approximate)
            try:
                cpu_usage = self.process.cpu_percent()
            except:
                cpu_usage = 0.0
            
            # Get test markers
            markers = [marker.name for marker in item.iter_markers()]
            
            # Record the test execution
            self.monitor.record_test_execution(
                test_name=self.current_test_name,
                duration=duration,
                status="passed",  # Will be updated by other hooks if failed
                memory_usage=max(0, memory_usage),
                cpu_usage=cpu_usage,
                markers=markers
            )
    
    def pytest_runtest_logreport(self, report):
        """Called when a test report is generated."""
        if report.when == "call" and self.current_test_name:
            # Update the status based on the report
            status = "passed" if report.passed else "failed" if report.failed else "skipped"
            error_message = str(report.longrepr) if report.failed else None
            
            # Find the most recent test execution and update it
            with self.monitor._lock:
                for metrics in reversed(self.monitor.test_metrics):
                    if metrics.test_name == self.current_test_name:
                        metrics.status = status
                        if error_message:
                            metrics.error_message = error_message
                        break


class TestMonitoringReporter:
    """Generate reports from test monitoring data."""
    
    def __init__(self, monitor: TestPerformanceMonitor):
        self.monitor = monitor
    
    def generate_html_report(self, output_path: str):
        """Generate an HTML report of test performance metrics."""
        report_data = self.monitor.get_test_reliability_report()
        
        html_content = self._create_html_report(report_data)
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(html_content)
    
    def _create_html_report(self, data: Dict[str, Any]) -> str:
        """Create HTML content for the report."""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Test Performance Monitoring Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .summary {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
        .metric {{ display: inline-block; margin: 10px; padding: 10px; background: white; border-radius: 3px; }}
        .slow-tests, .unreliable-tests, .regressions {{ margin: 20px 0; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .recommendations {{ background: #fff3cd; padding: 15px; border-radius: 5px; }}
        .pass-rate-good {{ color: green; }}
        .pass-rate-warning {{ color: orange; }}
        .pass-rate-bad {{ color: red; }}
    </style>
</head>
<body>
    <h1>Test Performance Monitoring Report</h1>
    <p>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    
    <div class="summary">
        <h2>Summary</h2>
        <div class="metric">
            <strong>Total Executions:</strong> {data['summary']['total_executions']}
        </div>
        <div class="metric">
            <strong>Pass Rate:</strong> 
            <span class="{'pass-rate-good' if data['summary']['overall_pass_rate'] >= 0.95 else 'pass-rate-warning' if data['summary']['overall_pass_rate'] >= 0.8 else 'pass-rate-bad'}">
                {data['summary']['overall_pass_rate']:.1%}
            </span>
        </div>
        <div class="metric">
            <strong>Average Duration:</strong> {data['summary']['average_duration']:.2f}s
        </div>
    </div>
    
    <div class="slow-tests">
        <h2>Slow Tests (Top 10)</h2>
        <table>
            <tr><th>Test Name</th><th>Average Duration (s)</th><th>Median Duration (s)</th></tr>
            {''.join(f'<tr><td>{test[0]}</td><td>{test[1]:.2f}</td><td>{test[2]:.2f}</td></tr>' for test in data['slow_tests'])}
        </table>
    </div>
    
    <div class="unreliable-tests">
        <h2>Unreliable Tests (Top 10)</h2>
        <table>
            <tr><th>Test Name</th><th>Pass Rate</th><th>Total Runs</th><th>Failed Runs</th></tr>
            {''.join(f'<tr><td>{test[0]}</td><td>{test[1]:.1%}</td><td>{test[2]}</td><td>{test[3]}</td></tr>' for test in data['unreliable_tests'])}
        </table>
    </div>
    
    <div class="regressions">
        <h2>Performance Regressions (Top 10)</h2>
        <table>
            <tr><th>Test Name</th><th>Regression Factor</th><th>Recent Avg (s)</th><th>Historical Avg (s)</th></tr>
            {''.join(f'<tr><td>{reg["test_name"]}</td><td>{reg["regression_factor"]:.2f}x</td><td>{reg["recent_avg_duration"]:.2f}</td><td>{reg["historical_avg_duration"]:.2f}</td></tr>' for reg in data['performance_regressions'])}
        </table>
    </div>
    
    <div class="recommendations">
        <h2>Recommendations</h2>
        <ul>
            {''.join(f'<li>{rec}</li>' for rec in data['recommendations'])}
        </ul>
    </div>
</body>
</html>
        """
        return html
    
    def generate_json_report(self, output_path: str):
        """Generate a JSON report of test performance metrics."""
        report_data = self.monitor.get_test_reliability_report()
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(report_data, f, indent=2)
    
    def print_summary_report(self):
        """Print a summary report to console."""
        report_data = self.monitor.get_test_reliability_report()
        
        print("\n" + "="*60)
        print("TEST PERFORMANCE MONITORING SUMMARY")
        print("="*60)
        
        summary = report_data['summary']
        print(f"Total Test Executions: {summary['total_executions']}")
        print(f"Overall Pass Rate: {summary['overall_pass_rate']:.1%}")
        print(f"Average Duration: {summary['average_duration']:.2f}s")
        
        if summary.get('memory_usage'):
            mem = summary['memory_usage']
            print(f"Memory Usage - Avg: {mem['average_mb']:.1f}MB, Peak: {mem['max_mb']:.1f}MB")
        
        print(f"\nStatus Distribution:")
        for status, count in summary['status_distribution'].items():
            print(f"  {status.capitalize()}: {count}")
        
        if report_data['slow_tests']:
            print(f"\nSlow Tests ({len(report_data['slow_tests'])}):")
            for test_name, avg_duration, _ in report_data['slow_tests'][:5]:
                print(f"  {test_name}: {avg_duration:.2f}s")
        
        if report_data['unreliable_tests']:
            print(f"\nUnreliable Tests ({len(report_data['unreliable_tests'])}):")
            for test_name, pass_rate, total_runs, failed_runs in report_data['unreliable_tests'][:5]:
                print(f"  {test_name}: {pass_rate:.1%} pass rate ({failed_runs}/{total_runs} failed)")
        
        if report_data['performance_regressions']:
            print(f"\nPerformance Regressions ({len(report_data['performance_regressions'])}):")
            for regression in report_data['performance_regressions'][:5]:
                print(f"  {regression['test_name']}: {regression['regression_factor']:.2f}x slower")
        
        if report_data['recommendations']:
            print(f"\nRecommendations:")
            for rec in report_data['recommendations']:
                print(f"  • {rec}")
        
        print("="*60)


# Global monitoring instances
_performance_monitor = TestPerformanceMonitor()
_monitoring_reporter = TestMonitoringReporter(_performance_monitor)


def get_performance_monitor() -> TestPerformanceMonitor:
    """Get the global performance monitor."""
    return _performance_monitor


def get_monitoring_reporter() -> TestMonitoringReporter:
    """Get the global monitoring reporter."""
    return _monitoring_reporter


# Pytest plugin for automatic monitoring
class TestMonitoringPlugin:
    """Pytest plugin for automatic test monitoring."""
    
    def __init__(self):
        self.tracker = TestExecutionTracker(_performance_monitor)
        self.suite_start_time = None
        self.suite_test_results = []
    
    def pytest_sessionstart(self, session):
        """Called at the start of the test session."""
        self.suite_start_time = time.time()
        self.suite_test_results = []
    
    def pytest_sessionfinish(self, session, exitstatus):
        """Called at the end of the test session."""
        if self.suite_start_time and self.suite_test_results:
            suite_duration = time.time() - self.suite_start_time
            _performance_monitor.record_suite_execution("test_session", self.suite_test_results)
            
            # Generate reports
            reports_dir = Path("test_reports")
            reports_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            _monitoring_reporter.generate_html_report(f"test_reports/performance_report_{timestamp}.html")
            _monitoring_reporter.generate_json_report(f"test_reports/performance_report_{timestamp}.json")
            _performance_monitor.export_metrics(f"test_reports/test_metrics_{timestamp}.json")
            
            # Print summary
            _monitoring_reporter.print_summary_report()
    
    def pytest_runtest_setup(self, item):
        """Forward to tracker."""
        self.tracker.pytest_runtest_setup(item)
    
    def pytest_runtest_call(self, item):
        """Forward to tracker."""
        self.tracker.pytest_runtest_call(item)
    
    def pytest_runtest_teardown(self, item, nextitem):
        """Forward to tracker."""
        self.tracker.pytest_runtest_teardown(item, nextitem)
    
    def pytest_runtest_logreport(self, report):
        """Forward to tracker and collect results."""
        self.tracker.pytest_runtest_logreport(report)
        
        # Collect test results for suite metrics
        if report.when == "call":
            # Find the corresponding test metrics
            with _performance_monitor._lock:
                for metrics in reversed(_performance_monitor.test_metrics):
                    if metrics.test_name == report.nodeid:
                        self.suite_test_results.append(metrics)
                        break


# Function to register the plugin
def pytest_configure(config):
    """Register the monitoring plugin with pytest."""
    if not hasattr(config, '_test_monitoring_plugin'):
        config._test_monitoring_plugin = TestMonitoringPlugin()
        config.pluginmanager.register(config._test_monitoring_plugin, "test_monitoring")


# Decorators for manual monitoring
def monitor_test_performance(func):
    """Decorator to manually monitor test performance."""
    def wrapper(*args, **kwargs):
        start_time = time.time()
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024
        
        try:
            result = func(*args, **kwargs)
            status = "passed"
            error_message = None
        except Exception as e:
            status = "failed"
            error_message = str(e)
            result = None
            raise
        finally:
            duration = time.time() - start_time
            final_memory = process.memory_info().rss / 1024 / 1024
            memory_usage = final_memory - initial_memory
            
            _performance_monitor.record_test_execution(
                test_name=func.__name__,
                duration=duration,
                status=status,
                memory_usage=max(0, memory_usage),
                error_message=error_message
            )
        
        return result
    
    return wrapper


# Utility functions
def create_performance_baseline(test_pattern: str = "*", runs: int = 5):
    """Create performance baselines for tests."""
    # This would typically run tests multiple times to establish baselines
    # Implementation would depend on specific test runner integration
    pass


def analyze_test_trends(days: int = 7) -> Dict[str, Any]:
    """Analyze test performance trends over time."""
    cutoff_time = time.time() - (days * 24 * 60 * 60)
    
    with _performance_monitor._lock:
        recent_metrics = [m for m in _performance_monitor.test_metrics if m.timestamp >= cutoff_time]
    
    if not recent_metrics:
        return {"error": "No recent test data available"}
    
    # Group by day
    daily_metrics = defaultdict(list)
    for metrics in recent_metrics:
        day = datetime.fromtimestamp(metrics.timestamp).date()
        daily_metrics[day].append(metrics)
    
    # Calculate daily statistics
    daily_stats = {}
    for day, metrics in daily_metrics.items():
        total_tests = len(metrics)
        passed_tests = sum(1 for m in metrics if m.status == "passed")
        avg_duration = statistics.mean([m.duration for m in metrics])
        
        daily_stats[day.isoformat()] = {
            "total_tests": total_tests,
            "pass_rate": passed_tests / total_tests if total_tests > 0 else 0,
            "average_duration": avg_duration
        }
    
    return {
        "period_days": days,
        "daily_statistics": daily_stats,
        "total_executions": len(recent_metrics),
        "trend_analysis": "Trends would be calculated here with more sophisticated analysis"
    }