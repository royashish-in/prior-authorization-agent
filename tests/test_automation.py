"""
Test automation scripts and continuous integration setup.

Provides utilities for automated testing, test reporting, and CI/CD integration.
"""

import os
import sys
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional
import pytest


class Automation:
    """Automated testing utilities and CI/CD integration."""
    
    def __init__(self, project_root: Optional[str] = None):
        """Initialize test automation."""
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.test_results_dir = self.project_root / "test_results"
        self.test_results_dir.mkdir(exist_ok=True)
        
        # Test configuration
        self.test_config = {
            "coverage_threshold": 90,
            "performance_timeout": 300,  # 5 minutes
            "load_test_timeout": 600,    # 10 minutes
            "max_retries": 3
        }
    
    def run_unit_tests(self, coverage: bool = True, verbose: bool = True) -> Dict[str, Any]:
        """Run unit tests with coverage reporting."""
        print("Running unit tests...")
        
        cmd = ["python", "-m", "pytest", "tests/", "-m", "unit"]
        
        if coverage:
            cmd.extend([
                "--cov=src",
                "--cov-report=term-missing",
                "--cov-report=html:htmlcov",
                f"--cov-fail-under={self.test_config['coverage_threshold']}"
            ])
        
        if verbose:
            cmd.append("-v")
        
        # Add test result output
        junit_file = self.test_results_dir / "unit_tests.xml"
        cmd.extend(["--junit-xml", str(junit_file)])
        
        start_time = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True)
        end_time = time.time()
        
        return {
            "test_type": "unit",
            "success": result.returncode == 0,
            "duration": end_time - start_time,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "junit_file": str(junit_file)
        }
    
    def run_integration_tests(self, verbose: bool = True) -> Dict[str, Any]:
        """Run integration tests."""
        print("Running integration tests...")
        
        cmd = ["python", "-m", "pytest", "tests/", "-m", "integration"]
        
        if verbose:
            cmd.append("-v")
        
        # Add test result output
        junit_file = self.test_results_dir / "integration_tests.xml"
        cmd.extend(["--junit-xml", str(junit_file)])
        
        start_time = time.time()
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True,
            timeout=self.test_config["performance_timeout"]
        )
        end_time = time.time()
        
        return {
            "test_type": "integration",
            "success": result.returncode == 0,
            "duration": end_time - start_time,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "junit_file": str(junit_file)
        }
    
    def run_performance_tests(self, verbose: bool = True) -> Dict[str, Any]:
        """Run performance tests."""
        print("Running performance tests...")
        
        cmd = ["python", "-m", "pytest", "tests/", "-m", "performance", "--tb=short"]
        
        if verbose:
            cmd.append("-v")
        
        # Add test result output
        junit_file = self.test_results_dir / "performance_tests.xml"
        cmd.extend(["--junit-xml", str(junit_file)])
        
        start_time = time.time()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.test_config["load_test_timeout"]
        )
        end_time = time.time()
        
        return {
            "test_type": "performance",
            "success": result.returncode == 0,
            "duration": end_time - start_time,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "junit_file": str(junit_file)
        }
    
    def run_security_tests(self, verbose: bool = True) -> Dict[str, Any]:
        """Run security tests."""
        print("Running security tests...")
        
        cmd = ["python", "-m", "pytest", "tests/", "-m", "security"]
        
        if verbose:
            cmd.append("-v")
        
        # Add test result output
        junit_file = self.test_results_dir / "security_tests.xml"
        cmd.extend(["--junit-xml", str(junit_file)])
        
        start_time = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True)
        end_time = time.time()
        
        return {
            "test_type": "security",
            "success": result.returncode == 0,
            "duration": end_time - start_time,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "junit_file": str(junit_file)
        }
    
    def run_all_tests(self, include_slow: bool = False) -> Dict[str, Any]:
        """Run all test suites."""
        print("Running complete test suite...")
        
        test_results = []
        overall_success = True
        total_duration = 0
        
        # Run unit tests
        unit_result = self.run_unit_tests()
        test_results.append(unit_result)
        overall_success &= unit_result["success"]
        total_duration += unit_result["duration"]
        
        # Run integration tests
        integration_result = self.run_integration_tests()
        test_results.append(integration_result)
        overall_success &= integration_result["success"]
        total_duration += integration_result["duration"]
        
        # Run security tests
        security_result = self.run_security_tests()
        test_results.append(security_result)
        overall_success &= security_result["success"]
        total_duration += security_result["duration"]
        
        # Run performance tests (if requested)
        if include_slow:
            performance_result = self.run_performance_tests()
            test_results.append(performance_result)
            overall_success &= performance_result["success"]
            total_duration += performance_result["duration"]
        
        # Generate summary report
        summary = {
            "overall_success": overall_success,
            "total_duration": total_duration,
            "test_results": test_results,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": self._generate_test_summary(test_results)
        }
        
        # Save summary report
        summary_file = self.test_results_dir / "test_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        return summary
    
    def run_coverage_analysis(self) -> Dict[str, Any]:
        """Run detailed coverage analysis."""
        print("Running coverage analysis...")
        
        cmd = [
            "python", "-m", "pytest", "tests/",
            "--cov=src",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov",
            "--cov-report=json:coverage.json",
            "--cov-report=xml:coverage.xml"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Parse coverage results
        coverage_data = {}
        coverage_file = self.project_root / "coverage.json"
        
        if coverage_file.exists():
            with open(coverage_file, 'r') as f:
                coverage_data = json.load(f)
        
        return {
            "success": result.returncode == 0,
            "coverage_data": coverage_data,
            "html_report": "htmlcov/index.html",
            "xml_report": "coverage.xml"
        }
    
    def run_linting_and_formatting(self) -> Dict[str, Any]:
        """Run code linting and formatting checks."""
        print("Running linting and formatting checks...")
        
        results = {}
        
        # Run Black formatting check
        black_result = subprocess.run(
            ["python", "-m", "black", "--check", "src/", "tests/"],
            capture_output=True, text=True
        )
        results["black"] = {
            "success": black_result.returncode == 0,
            "output": black_result.stdout + black_result.stderr
        }
        
        # Run flake8 linting
        flake8_result = subprocess.run(
            ["python", "-m", "flake8", "src/", "tests/"],
            capture_output=True, text=True
        )
        results["flake8"] = {
            "success": flake8_result.returncode == 0,
            "output": flake8_result.stdout + flake8_result.stderr
        }
        
        # Run mypy type checking
        mypy_result = subprocess.run(
            ["python", "-m", "mypy", "src/"],
            capture_output=True, text=True
        )
        results["mypy"] = {
            "success": mypy_result.returncode == 0,
            "output": mypy_result.stdout + mypy_result.stderr
        }
        
        overall_success = all(r["success"] for r in results.values())
        
        return {
            "overall_success": overall_success,
            "results": results
        }
    
    def generate_test_report(self, test_results: Dict[str, Any]) -> str:
        """Generate a comprehensive test report."""
        report_lines = [
            "# Prior Authorization System - Test Report",
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "",
            "## Summary",
            f"Overall Status: {'✅ PASSED' if test_results['overall_success'] else '❌ FAILED'}",
            f"Total Duration: {test_results['total_duration']:.2f} seconds",
            ""
        ]
        
        # Add individual test results
        for result in test_results["test_results"]:
            status = "✅ PASSED" if result["success"] else "❌ FAILED"
            report_lines.extend([
                f"### {result['test_type'].title()} Tests",
                f"Status: {status}",
                f"Duration: {result['duration']:.2f} seconds",
                ""
            ])
            
            if not result["success"] and result["stderr"]:
                report_lines.extend([
                    "**Errors:**",
                    "```",
                    result["stderr"][:1000] + ("..." if len(result["stderr"]) > 1000 else ""),
                    "```",
                    ""
                ])
        
        # Add summary statistics
        if "summary" in test_results:
            summary = test_results["summary"]
            report_lines.extend([
                "## Test Statistics",
                f"- Total Tests: {summary.get('total_tests', 'N/A')}",
                f"- Passed: {summary.get('passed_tests', 'N/A')}",
                f"- Failed: {summary.get('failed_tests', 'N/A')}",
                f"- Coverage: {summary.get('coverage_percentage', 'N/A')}%",
                ""
            ])
        
        return "\n".join(report_lines)
    
    def _generate_test_summary(self, test_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate summary statistics from test results."""
        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        
        for result in test_results:
            # Parse test counts from stdout (pytest output)
            if "passed" in result["stdout"]:
                # Simple parsing - in production, would use pytest-json-report
                pass
        
        return {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "success_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0
        }


class ContinuousIntegration:
    """CI/CD pipeline utilities."""
    
    def __init__(self):
        """Initialize CI utilities."""
        self.automation = Automation()
    
    def run_ci_pipeline(self, include_performance: bool = False) -> bool:
        """Run complete CI pipeline."""
        print("Starting CI pipeline...")
        
        pipeline_steps = [
            ("Linting and Formatting", self.automation.run_linting_and_formatting),
            ("Unit Tests", self.automation.run_unit_tests),
            ("Integration Tests", self.automation.run_integration_tests),
            ("Security Tests", self.automation.run_security_tests),
            ("Coverage Analysis", self.automation.run_coverage_analysis)
        ]
        
        if include_performance:
            pipeline_steps.append(("Performance Tests", self.automation.run_performance_tests))
        
        all_passed = True
        
        for step_name, step_function in pipeline_steps:
            print(f"\n{'='*50}")
            print(f"Running: {step_name}")
            print('='*50)
            
            try:
                result = step_function()
                success = result.get("success", result.get("overall_success", False))
                
                if success:
                    print(f"✅ {step_name} PASSED")
                else:
                    print(f"❌ {step_name} FAILED")
                    all_passed = False
                    
                    # Print error details
                    if "stderr" in result and result["stderr"]:
                        print("Error details:")
                        print(result["stderr"][:500])
                    elif "results" in result:
                        for tool, tool_result in result["results"].items():
                            if not tool_result["success"]:
                                print(f"{tool} failed:")
                                print(tool_result["output"][:300])
                
            except Exception as e:
                print(f"❌ {step_name} FAILED with exception: {e}")
                all_passed = False
        
        print(f"\n{'='*50}")
        if all_passed:
            print("🎉 CI PIPELINE PASSED")
        else:
            print("💥 CI PIPELINE FAILED")
        print('='*50)
        
        return all_passed
    
    def setup_github_actions(self) -> str:
        """Generate GitHub Actions workflow configuration."""
        workflow = """
name: Prior Authorization System CI

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    
    strategy:
      matrix:
        python-version: [3.11, 3.12]
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v3
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
    
    - name: Run linting
      run: |
        python -m black --check src/ tests/
        python -m flake8 src/ tests/
        python -m mypy src/
    
    - name: Run unit tests
      run: |
        python -m pytest tests/ -m unit --cov=src --cov-report=xml
    
    - name: Run integration tests
      run: |
        python -m pytest tests/ -m integration
    
    - name: Run security tests
      run: |
        python -m pytest tests/ -m security
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        flags: unittests
        name: codecov-umbrella
        fail_ci_if_error: true

  performance:
    runs-on: ubuntu-latest
    needs: test
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python 3.11
      uses: actions/setup-python@v3
      with:
        python-version: 3.11
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
    
    - name: Run performance tests
      run: |
        python -m pytest tests/ -m performance --tb=short
"""
        
        # Write workflow file
        workflow_dir = Path(".github/workflows")
        workflow_dir.mkdir(parents=True, exist_ok=True)
        
        workflow_file = workflow_dir / "ci.yml"
        with open(workflow_file, 'w') as f:
            f.write(workflow)
        
        return str(workflow_file)


def main():
    """Main entry point for test automation."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Prior Authorization System Test Automation")
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    parser.add_argument("--performance", action="store_true", help="Run performance tests only")
    parser.add_argument("--security", action="store_true", help="Run security tests only")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    parser.add_argument("--ci", action="store_true", help="Run CI pipeline")
    parser.add_argument("--coverage", action="store_true", help="Run coverage analysis")
    parser.add_argument("--lint", action="store_true", help="Run linting and formatting")
    parser.add_argument("--setup-github", action="store_true", help="Setup GitHub Actions")
    
    args = parser.parse_args()
    
    automation = Automation()
    ci = ContinuousIntegration()
    
    if args.unit:
        result = automation.run_unit_tests()
        sys.exit(0 if result["success"] else 1)
    
    elif args.integration:
        result = automation.run_integration_tests()
        sys.exit(0 if result["success"] else 1)
    
    elif args.performance:
        result = automation.run_performance_tests()
        sys.exit(0 if result["success"] else 1)
    
    elif args.security:
        result = automation.run_security_tests()
        sys.exit(0 if result["success"] else 1)
    
    elif args.coverage:
        result = automation.run_coverage_analysis()
        print(f"Coverage analysis completed. HTML report: {result['html_report']}")
        sys.exit(0 if result["success"] else 1)
    
    elif args.lint:
        result = automation.run_linting_and_formatting()
        sys.exit(0 if result["overall_success"] else 1)
    
    elif args.ci:
        success = ci.run_ci_pipeline(include_performance=args.performance)
        sys.exit(0 if success else 1)
    
    elif args.setup_github:
        workflow_file = ci.setup_github_actions()
        print(f"GitHub Actions workflow created: {workflow_file}")
        sys.exit(0)
    
    elif args.all:
        result = automation.run_all_tests(include_slow=True)
        
        # Generate and save report
        report = automation.generate_test_report(result)
        report_file = automation.test_results_dir / "test_report.md"
        with open(report_file, 'w') as f:
            f.write(report)
        
        print(f"\nTest report saved to: {report_file}")
        sys.exit(0 if result["overall_success"] else 1)
    
    else:
        # Default: run basic test suite
        result = automation.run_all_tests(include_slow=False)
        sys.exit(0 if result["overall_success"] else 1)


if __name__ == "__main__":
    main()