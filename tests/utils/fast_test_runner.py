#!/usr/bin/env python3
"""
Fast test runner for optimized unit test execution.

This script provides utilities for running tests with performance optimizations,
including parallel execution, memory management, and performance monitoring.
"""

import os
import sys
import time
import subprocess
import argparse
from typing import List, Dict, Any, Optional
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.utils.performance_helpers import (
    get_performance_metrics, 
    create_performance_report,
    memory_optimizer
)


class FastTestRunner:
    """Optimized test runner for fast unit test execution."""
    
    def __init__(self):
        self.project_root = project_root
        self.test_results = {}
        self.performance_metrics = get_performance_metrics()
    
    def run_fast_tests(self, 
                      test_pattern: str = "test_*.py",
                      parallel: bool = True,
                      max_workers: int = 4,
                      timeout: int = 30,
                      verbose: bool = False) -> Dict[str, Any]:
        """Run fast unit tests with optimizations."""
        
        print("🚀 Starting fast test execution...")
        start_time = time.time()
        
        # Prepare environment
        self._prepare_test_environment()
        
        # Build pytest command
        cmd = self._build_pytest_command(
            test_pattern=test_pattern,
            parallel=parallel,
            max_workers=max_workers,
            timeout=timeout,
            verbose=verbose
        )
        
        print(f"📋 Running command: {' '.join(cmd)}")
        
        # Execute tests
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=timeout * 60  # Convert to seconds
            )
            
            execution_time = time.time() - start_time
            
            # Process results
            test_results = self._process_test_results(result, execution_time)
            
            # Generate performance report
            if verbose:
                self._print_performance_report(test_results)
            
            return test_results
            
        except subprocess.TimeoutExpired:
            print(f"❌ Tests timed out after {timeout} minutes")
            return {"status": "timeout", "execution_time": timeout * 60}
        
        except Exception as e:
            print(f"❌ Test execution failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def run_unit_tests_only(self, verbose: bool = False) -> Dict[str, Any]:
        """Run only unit tests with maximum optimization."""
        return self.run_fast_tests(
            test_pattern="test_*.py",
            parallel=True,
            max_workers=6,
            timeout=10,  # 10 minutes max for unit tests
            verbose=verbose
        )
    
    def run_performance_benchmark(self) -> Dict[str, Any]:
        """Run performance benchmark tests."""
        print("📊 Running performance benchmark...")
        
        # Run tests multiple times to get average
        results = []
        for i in range(3):
            print(f"🔄 Benchmark run {i + 1}/3...")
            result = self.run_fast_tests(
                test_pattern="test_*.py",
                parallel=False,  # Single-threaded for consistent timing
                max_workers=1,
                timeout=15,
                verbose=False
            )
            results.append(result)
        
        # Calculate averages
        avg_time = sum(r.get("execution_time", 0) for r in results) / len(results)
        avg_tests = sum(r.get("tests_run", 0) for r in results) / len(results)
        
        benchmark_results = {
            "average_execution_time": round(avg_time, 2),
            "average_tests_run": int(avg_tests),
            "tests_per_second": round(avg_tests / avg_time, 2) if avg_time > 0 else 0,
            "individual_runs": results
        }
        
        print(f"📈 Benchmark Results:")
        print(f"   Average execution time: {benchmark_results['average_execution_time']}s")
        print(f"   Average tests run: {benchmark_results['average_tests_run']}")
        print(f"   Tests per second: {benchmark_results['tests_per_second']}")
        
        return benchmark_results
    
    def _prepare_test_environment(self):
        """Prepare the test environment for optimal performance."""
        # Set environment variables for testing
        os.environ.update({
            'PHI_MASTER_KEY': 'test-phi-master-key-for-testing-purposes-2024',
            'PA_SECRET_KEY': 'test-secret-key-for-testing-12345678901234567890',
            'PA_ENCRYPTION_KEY': 'test-encryption-key-32-chars-long',
            'PA_ENVIRONMENT': 'testing',
            'PA_DATABASE_URL': 'sqlite:///:memory:',
            'PA_LOG_LEVEL': 'ERROR',
            'PYTEST_CURRENT_TEST': 'true'
        })
        
        # Optimize memory settings
        memory_optimizer.optimize_garbage_collection()
    
    def _build_pytest_command(self,
                             test_pattern: str,
                             parallel: bool,
                             max_workers: int,
                             timeout: int,
                             verbose: bool) -> List[str]:
        """Build the pytest command with optimizations."""
        cmd = [
            sys.executable, "-m", "pytest",
            "-c", "pytest-fast.ini",  # Use fast configuration
            "--tb=short",
            "--maxfail=5",
            "-x",  # Stop on first failure
            "--disable-warnings",
            "-m", "not slow and not integration and not external",
            "--no-cov",  # Disable coverage for speed
        ]
        
        if verbose:
            cmd.append("-v")
        else:
            cmd.append("-q")
        
        if parallel and max_workers > 1:
            try:
                import pytest_xdist
                cmd.extend(["-n", str(max_workers)])
            except ImportError:
                print("⚠️  pytest-xdist not available, running tests sequentially")
        
        # Add durations reporting for performance monitoring
        cmd.extend(["--durations=10"])
        
        # Add test pattern
        cmd.append(f"tests/{test_pattern}")
        
        return cmd
    
    def _process_test_results(self, result: subprocess.CompletedProcess, execution_time: float) -> Dict[str, Any]:
        """Process test execution results."""
        output_lines = result.stdout.split('\n')
        
        # Parse pytest output
        tests_run = 0
        tests_passed = 0
        tests_failed = 0
        tests_skipped = 0
        
        for line in output_lines:
            if "passed" in line and "failed" in line:
                # Parse summary line like "5 failed, 95 passed in 10.23s"
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "passed":
                        tests_passed = int(parts[i-1])
                    elif part == "failed":
                        tests_failed = int(parts[i-1])
                    elif part == "skipped":
                        tests_skipped = int(parts[i-1])
        
        tests_run = tests_passed + tests_failed + tests_skipped
        
        # Determine status
        if result.returncode == 0:
            status = "passed"
        elif tests_failed > 0:
            status = "failed"
        else:
            status = "error"
        
        return {
            "status": status,
            "return_code": result.returncode,
            "execution_time": round(execution_time, 2),
            "tests_run": tests_run,
            "tests_passed": tests_passed,
            "tests_failed": tests_failed,
            "tests_skipped": tests_skipped,
            "tests_per_second": round(tests_run / execution_time, 2) if execution_time > 0 else 0,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    
    def _print_performance_report(self, results: Dict[str, Any]):
        """Print detailed performance report."""
        print("\n📊 Performance Report:")
        print(f"   Status: {results['status']}")
        print(f"   Execution time: {results['execution_time']}s")
        print(f"   Tests run: {results['tests_run']}")
        print(f"   Tests passed: {results['tests_passed']}")
        print(f"   Tests failed: {results['tests_failed']}")
        print(f"   Tests skipped: {results['tests_skipped']}")
        print(f"   Tests per second: {results['tests_per_second']}")
        
        # Check performance targets
        if results['execution_time'] <= 30:
            print("✅ Unit test execution time target met (≤30s)")
        else:
            print(f"❌ Unit test execution time target missed (>{30}s)")
        
        if results['tests_per_second'] >= 10:
            print("✅ Test throughput target met (≥10 tests/s)")
        else:
            print(f"⚠️  Test throughput below target (<10 tests/s)")


def main():
    """Main entry point for the fast test runner."""
    parser = argparse.ArgumentParser(description="Fast test runner for optimized unit test execution")
    parser.add_argument("--pattern", default="test_*.py", help="Test file pattern")
    parser.add_argument("--parallel", action="store_true", default=True, help="Run tests in parallel")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout in minutes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--benchmark", action="store_true", help="Run performance benchmark")
    parser.add_argument("--unit-only", action="store_true", help="Run only unit tests")
    
    args = parser.parse_args()
    
    runner = FastTestRunner()
    
    if args.benchmark:
        results = runner.run_performance_benchmark()
    elif args.unit_only:
        results = runner.run_unit_tests_only(verbose=args.verbose)
    else:
        results = runner.run_fast_tests(
            test_pattern=args.pattern,
            parallel=args.parallel,
            max_workers=args.workers,
            timeout=args.timeout,
            verbose=args.verbose
        )
    
    # Exit with appropriate code
    if results.get("status") == "passed":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()