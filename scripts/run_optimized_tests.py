#!/usr/bin/env python3
"""
Optimized test execution script with performance monitoring and parallel execution.

This script provides optimized test execution with:
- Parallel execution for compatible tests
- Performance monitoring and reporting
- Resource optimization
- Timeout management
- Reliability enhancements
"""

import os
import sys
import time
import argparse
import subprocess
import json
import threading
from pathlib import Path
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OptimizedTestRunner:
    """Optimized test runner with parallel execution and performance monitoring."""
    
    def __init__(self, max_workers: int = 4, timeout: int = 60):
        self.max_workers = max_workers
        self.timeout = timeout
        self.test_results = {}
        self.performance_metrics = {}
        self.failed_tests = []
        self.slow_tests = []
        self.total_start_time = None
        self.total_end_time = None
    
    def discover_tests(self, test_path: str = "tests") -> Dict[str, List[str]]:
        """Discover and categorize tests for optimal execution."""
        test_files = []
        test_dir = Path(test_path)
        
        if test_dir.exists():
            for test_file in test_dir.rglob("test_*.py"):
                if not any(skip in str(test_file) for skip in ["__pycache__", ".pyc"]):
                    test_files.append(str(test_file))
        
        # Categorize tests based on patterns and markers
        categorized_tests = {
            "fast_unit": [],
            "integration": [],
            "slow": [],
            "parallel_safe": [],
            "serial_required": []
        }
        
        for test_file in test_files:
            category = self._categorize_test_file(test_file)
            categorized_tests[category].append(test_file)
        
        return categorized_tests
    
    def _categorize_test_file(self, test_file: str) -> str:
        """Categorize a test file based on its name and content patterns."""
        file_path = Path(test_file)
        file_name = file_path.name.lower()
        
        # Check for integration tests
        if any(pattern in file_name for pattern in [
            "integration", "comprehensive", "system", "end_to_end"
        ]):
            return "integration"
        
        # Check for slow tests
        if any(pattern in file_name for pattern in [
            "performance", "load", "stress", "benchmark"
        ]):
            return "slow"
        
        # Check for tests that require serial execution
        if any(pattern in file_name for pattern in [
            "database", "migration", "config", "singleton"
        ]):
            return "serial_required"
        
        # Check for fast unit tests
        if any(pattern in file_name for pattern in [
            "unit", "util", "helper", "mock", "fixture"
        ]):
            return "fast_unit"
        
        # Default to parallel safe
        return "parallel_safe"
    
    def run_test_category(self, category: str, test_files: List[str], 
                         pytest_args: List[str] = None) -> Dict[str, Any]:
        """Run tests in a specific category with appropriate optimization."""
        if not test_files:
            return {"category": category, "status": "skipped", "reason": "no_tests"}
        
        pytest_args = pytest_args or []
        start_time = time.perf_counter()
        
        logger.info(f"Running {category} tests: {len(test_files)} files")
        
        if category == "fast_unit":
            result = self._run_fast_unit_tests(test_files, pytest_args)
        elif category == "integration":
            result = self._run_integration_tests(test_files, pytest_args)
        elif category == "slow":
            result = self._run_slow_tests(test_files, pytest_args)
        elif category == "parallel_safe":
            result = self._run_parallel_tests(test_files, pytest_args)
        elif category == "serial_required":
            result = self._run_serial_tests(test_files, pytest_args)
        else:
            result = self._run_default_tests(test_files, pytest_args)
        
        duration = time.perf_counter() - start_time
        result["duration"] = duration
        result["category"] = category
        
        logger.info(f"Completed {category} tests in {duration:.2f}s")
        return result
    
    def _run_fast_unit_tests(self, test_files: List[str], pytest_args: List[str]) -> Dict[str, Any]:
        """Run fast unit tests with maximum optimization."""
        cmd = [
            "python", "-m", "pytest",
            "-c", "pytest-fast.ini",
            "--tb=short",
            "--maxfail=5",
            "--timeout=5",
            "-v"
        ] + pytest_args + test_files
        
        return self._execute_pytest_command(cmd, "fast_unit")
    
    def _run_integration_tests(self, test_files: List[str], pytest_args: List[str]) -> Dict[str, Any]:
        """Run integration tests with database optimization."""
        cmd = [
            "python", "-m", "pytest",
            "-c", "pytest.ini",
            "--tb=short",
            "--maxfail=3",
            "--timeout=30",
            "-v",
            "-m", "not slow"
        ] + pytest_args + test_files
        
        return self._execute_pytest_command(cmd, "integration")
    
    def _run_slow_tests(self, test_files: List[str], pytest_args: List[str]) -> Dict[str, Any]:
        """Run slow tests with extended timeout."""
        cmd = [
            "python", "-m", "pytest",
            "-c", "pytest.ini",
            "--tb=short",
            "--maxfail=1",
            "--timeout=120",
            "-v",
            "-s"  # Don't capture output for slow tests
        ] + pytest_args + test_files
        
        return self._execute_pytest_command(cmd, "slow")
    
    def _run_parallel_tests(self, test_files: List[str], pytest_args: List[str]) -> Dict[str, Any]:
        """Run parallel-safe tests with concurrency."""
        # Check if pytest-xdist is available
        try:
            import pytest_xdist
            parallel_args = ["-n", "auto"]
        except ImportError:
            logger.warning("pytest-xdist not available, running tests serially")
            parallel_args = []
        
        cmd = [
            "python", "-m", "pytest",
            "-c", "pytest-parallel.ini",
            "--tb=short",
            "--maxfail=10",
            "--timeout=60",
            "-v"
        ] + parallel_args + pytest_args + test_files
        
        return self._execute_pytest_command(cmd, "parallel")
    
    def _run_serial_tests(self, test_files: List[str], pytest_args: List[str]) -> Dict[str, Any]:
        """Run tests that require serial execution."""
        cmd = [
            "python", "-m", "pytest",
            "-c", "pytest.ini",
            "--tb=short",
            "--maxfail=3",
            "--timeout=60",
            "-v",
            "-x"  # Stop on first failure for serial tests
        ] + pytest_args + test_files
        
        return self._execute_pytest_command(cmd, "serial")
    
    def _run_default_tests(self, test_files: List[str], pytest_args: List[str]) -> Dict[str, Any]:
        """Run tests with default configuration."""
        cmd = [
            "python", "-m", "pytest",
            "-c", "pytest.ini",
            "--tb=short",
            "--maxfail=5",
            "--timeout=60",
            "-v"
        ] + pytest_args + test_files
        
        return self._execute_pytest_command(cmd, "default")
    
    def _execute_pytest_command(self, cmd: List[str], category: str) -> Dict[str, Any]:
        """Execute a pytest command and capture results."""
        logger.debug(f"Executing command: {' '.join(cmd)}")
        
        start_time = time.perf_counter()
        
        try:
            # Set environment variables for optimal performance
            env = os.environ.copy()
            env.update({
                "PYTHONPATH": str(project_root),
                "PYTEST_CURRENT_TEST": category,
                "PA_ENVIRONMENT": "testing",
                "PA_LOG_LEVEL": "ERROR"  # Reduce log noise
            })
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout * 2,  # Allow extra time for category timeout
                env=env,
                cwd=project_root
            )
            
            duration = time.perf_counter() - start_time
            
            # Parse pytest output for metrics
            metrics = self._parse_pytest_output(result.stdout, result.stderr)
            
            return {
                "status": "passed" if result.returncode == 0 else "failed",
                "returncode": result.returncode,
                "duration": duration,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "metrics": metrics
            }
            
        except subprocess.TimeoutExpired as e:
            duration = time.perf_counter() - start_time
            logger.error(f"Test category {category} timed out after {duration:.2f}s")
            
            return {
                "status": "timeout",
                "returncode": -1,
                "duration": duration,
                "stdout": "",
                "stderr": f"Tests timed out after {self.timeout * 2}s",
                "metrics": {}
            }
        
        except Exception as e:
            duration = time.perf_counter() - start_time
            logger.error(f"Error running test category {category}: {e}")
            
            return {
                "status": "error",
                "returncode": -1,
                "duration": duration,
                "stdout": "",
                "stderr": str(e),
                "metrics": {}
            }
    
    def _parse_pytest_output(self, stdout: str, stderr: str) -> Dict[str, Any]:
        """Parse pytest output to extract metrics."""
        metrics = {
            "tests_collected": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "tests_skipped": 0,
            "tests_error": 0,
            "warnings": 0,
            "duration": 0.0
        }
        
        # Parse test results from output
        lines = stdout.split('\n') + stderr.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Look for test summary line
            if "passed" in line and ("failed" in line or "error" in line or "skipped" in line):
                # Example: "5 passed, 2 failed, 1 skipped in 10.23s"
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "passed" and i > 0:
                        try:
                            metrics["tests_passed"] = int(parts[i-1])
                        except (ValueError, IndexError):
                            pass
                    elif part == "failed" and i > 0:
                        try:
                            metrics["tests_failed"] = int(parts[i-1])
                        except (ValueError, IndexError):
                            pass
                    elif part == "skipped" and i > 0:
                        try:
                            metrics["tests_skipped"] = int(parts[i-1])
                        except (ValueError, IndexError):
                            pass
                    elif part == "error" and i > 0:
                        try:
                            metrics["tests_error"] = int(parts[i-1])
                        except (ValueError, IndexError):
                            pass
                    elif part.endswith("s") and "in" in parts[i-1:i+1]:
                        try:
                            metrics["duration"] = float(part[:-1])
                        except (ValueError, IndexError):
                            pass
            
            # Count warnings
            if "warning" in line.lower():
                metrics["warnings"] += 1
        
        # Calculate total tests
        metrics["tests_collected"] = (
            metrics["tests_passed"] + 
            metrics["tests_failed"] + 
            metrics["tests_skipped"] + 
            metrics["tests_error"]
        )
        
        return metrics
    
    def run_all_tests(self, test_path: str = "tests", pytest_args: List[str] = None) -> Dict[str, Any]:
        """Run all tests with optimal categorization and execution."""
        self.total_start_time = time.perf_counter()
        
        logger.info("Starting optimized test execution")
        
        # Discover and categorize tests
        categorized_tests = self.discover_tests(test_path)
        
        # Log test distribution
        for category, files in categorized_tests.items():
            logger.info(f"{category}: {len(files)} test files")
        
        # Run test categories in optimal order
        execution_order = [
            "fast_unit",      # Run fastest tests first
            "parallel_safe",  # Run parallel-safe tests
            "integration",    # Run integration tests
            "serial_required", # Run serial tests
            "slow"           # Run slow tests last
        ]
        
        category_results = {}
        total_metrics = {
            "tests_collected": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "tests_skipped": 0,
            "tests_error": 0,
            "warnings": 0
        }
        
        for category in execution_order:
            if category in categorized_tests:
                result = self.run_test_category(
                    category, 
                    categorized_tests[category], 
                    pytest_args
                )
                category_results[category] = result
                
                # Aggregate metrics
                if "metrics" in result:
                    for key in total_metrics:
                        total_metrics[key] += result["metrics"].get(key, 0)
                
                # Track failures and slow tests
                if result["status"] == "failed":
                    self.failed_tests.extend(categorized_tests[category])
                
                if result.get("duration", 0) > 30:  # Tests taking more than 30s
                    self.slow_tests.append((category, result.get("duration", 0)))
        
        self.total_end_time = time.perf_counter()
        total_duration = self.total_end_time - self.total_start_time
        
        # Generate summary
        summary = {
            "total_duration": total_duration,
            "category_results": category_results,
            "total_metrics": total_metrics,
            "failed_tests": self.failed_tests,
            "slow_tests": self.slow_tests,
            "success_rate": self._calculate_success_rate(total_metrics),
            "performance_summary": self._generate_performance_summary(category_results)
        }
        
        logger.info(f"Test execution completed in {total_duration:.2f}s")
        logger.info(f"Success rate: {summary['success_rate']:.1f}%")
        
        return summary
    
    def _calculate_success_rate(self, metrics: Dict[str, int]) -> float:
        """Calculate overall test success rate."""
        total_tests = metrics["tests_collected"]
        if total_tests == 0:
            return 0.0
        
        passed_tests = metrics["tests_passed"]
        return (passed_tests / total_tests) * 100
    
    def _generate_performance_summary(self, category_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate performance summary from category results."""
        total_duration = sum(
            result.get("duration", 0) for result in category_results.values()
        )
        
        fastest_category = min(
            category_results.items(),
            key=lambda x: x[1].get("duration", float('inf')),
            default=(None, {"duration": 0})
        )
        
        slowest_category = max(
            category_results.items(),
            key=lambda x: x[1].get("duration", 0),
            default=(None, {"duration": 0})
        )
        
        return {
            "total_test_time": total_duration,
            "fastest_category": {
                "name": fastest_category[0],
                "duration": fastest_category[1].get("duration", 0)
            },
            "slowest_category": {
                "name": slowest_category[0],
                "duration": slowest_category[1].get("duration", 0)
            },
            "categories_completed": len(category_results),
            "average_category_time": total_duration / len(category_results) if category_results else 0
        }
    
    def generate_report(self, results: Dict[str, Any], output_file: Optional[str] = None) -> str:
        """Generate a detailed test execution report."""
        report_lines = [
            "# Optimized Test Execution Report",
            f"Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Summary",
            f"- Total Duration: {results['total_duration']:.2f}s",
            f"- Success Rate: {results['success_rate']:.1f}%",
            f"- Tests Collected: {results['total_metrics']['tests_collected']}",
            f"- Tests Passed: {results['total_metrics']['tests_passed']}",
            f"- Tests Failed: {results['total_metrics']['tests_failed']}",
            f"- Tests Skipped: {results['total_metrics']['tests_skipped']}",
            f"- Warnings: {results['total_metrics']['warnings']}",
            ""
        ]
        
        # Category results
        report_lines.extend([
            "## Category Results",
            ""
        ])
        
        for category, result in results["category_results"].items():
            status_emoji = "✅" if result["status"] == "passed" else "❌"
            report_lines.extend([
                f"### {category} {status_emoji}",
                f"- Status: {result['status']}",
                f"- Duration: {result.get('duration', 0):.2f}s",
                f"- Tests: {result.get('metrics', {}).get('tests_collected', 0)}",
                ""
            ])
        
        # Performance summary
        perf = results["performance_summary"]
        report_lines.extend([
            "## Performance Summary",
            f"- Fastest Category: {perf['fastest_category']['name']} ({perf['fastest_category']['duration']:.2f}s)",
            f"- Slowest Category: {perf['slowest_category']['name']} ({perf['slowest_category']['duration']:.2f}s)",
            f"- Average Category Time: {perf['average_category_time']:.2f}s",
            ""
        ])
        
        # Failed tests
        if results["failed_tests"]:
            report_lines.extend([
                "## Failed Tests",
                ""
            ])
            for test_file in results["failed_tests"]:
                report_lines.append(f"- {test_file}")
            report_lines.append("")
        
        # Slow tests
        if results["slow_tests"]:
            report_lines.extend([
                "## Slow Test Categories (>30s)",
                ""
            ])
            for category, duration in results["slow_tests"]:
                report_lines.append(f"- {category}: {duration:.2f}s")
            report_lines.append("")
        
        # Recommendations
        report_lines.extend([
            "## Recommendations",
            ""
        ])
        
        if results["success_rate"] < 95:
            report_lines.append("- Consider investigating failed tests to improve reliability")
        
        if results["slow_tests"]:
            report_lines.append("- Consider optimizing slow test categories")
        
        if results["total_metrics"]["warnings"] > 10:
            report_lines.append("- Consider addressing test warnings to reduce noise")
        
        report_content = "\n".join(report_lines)
        
        if output_file:
            with open(output_file, 'w') as f:
                f.write(report_content)
            logger.info(f"Report saved to {output_file}")
        
        return report_content


def main():
    """Main entry point for optimized test execution."""
    parser = argparse.ArgumentParser(description="Run optimized tests with performance monitoring")
    parser.add_argument("--test-path", default="tests", help="Path to test directory")
    parser.add_argument("--max-workers", type=int, default=4, help="Maximum parallel workers")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout per test category (seconds)")
    parser.add_argument("--report", help="Output file for test report")
    parser.add_argument("--json-output", help="Output file for JSON results")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--category", choices=["fast_unit", "integration", "slow", "parallel_safe", "serial_required"], 
                       help="Run only specific test category")
    parser.add_argument("pytest_args", nargs="*", help="Additional pytest arguments")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create test runner
    runner = OptimizedTestRunner(
        max_workers=args.max_workers,
        timeout=args.timeout
    )
    
    try:
        if args.category:
            # Run specific category
            categorized_tests = runner.discover_tests(args.test_path)
            if args.category in categorized_tests:
                result = runner.run_test_category(
                    args.category,
                    categorized_tests[args.category],
                    args.pytest_args
                )
                
                print(f"\nCategory: {args.category}")
                print(f"Status: {result['status']}")
                print(f"Duration: {result.get('duration', 0):.2f}s")
                
                if result['status'] != 'passed':
                    print(f"Error: {result.get('stderr', 'Unknown error')}")
                    sys.exit(1)
            else:
                print(f"No tests found for category: {args.category}")
                sys.exit(1)
        else:
            # Run all tests
            results = runner.run_all_tests(args.test_path, args.pytest_args)
            
            # Generate and display report
            report = runner.generate_report(results, args.report)
            
            if not args.report:
                print("\n" + report)
            
            # Save JSON output if requested
            if args.json_output:
                with open(args.json_output, 'w') as f:
                    json.dump(results, f, indent=2, default=str)
                logger.info(f"JSON results saved to {args.json_output}")
            
            # Exit with error code if tests failed
            if results["success_rate"] < 100:
                sys.exit(1)
    
    except KeyboardInterrupt:
        logger.info("Test execution interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Test execution failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()