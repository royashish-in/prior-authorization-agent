#!/usr/bin/env python3
"""
Test quality metrics and validation system for the Prior Authorization System test suite.

This module provides comprehensive test quality assessment including test reliability,
maintainability, documentation quality, and adherence to best practices.
"""

import os
import ast
import re
import json
import sqlite3
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, asdict
from pathlib import Path
import xml.etree.ElementTree as ET


@dataclass
class TestQualityMetrics:
    """Comprehensive test quality metrics."""
    timestamp: str
    total_tests: int
    test_reliability_score: float  # 0-100
    documentation_quality_score: float  # 0-100
    maintainability_score: float  # 0-100
    performance_score: float  # 0-100
    compliance_score: float  # 0-100
    overall_quality_score: float  # 0-100
    
    # Detailed metrics
    tests_with_docstrings: int
    tests_with_comprehensive_docs: int
    slow_tests_count: int
    flaky_tests_count: int
    phi_compliant_tests: int
    properly_marked_tests: int
    
    # Quality issues
    quality_issues: List[str]
    recommendations: List[str]


@dataclass
class TestFileAnalysis:
    """Analysis results for a single test file."""
    file_path: str
    total_methods: int
    documented_methods: int
    comprehensive_docs: int
    proper_naming: int
    proper_markers: int
    phi_compliant: int
    performance_issues: List[str]
    quality_issues: List[str]
    maintainability_score: float


class TestQualityAnalyzer:
    """Analyzes test quality across multiple dimensions."""
    
    def __init__(self, tests_directory: str = "tests"):
        self.tests_directory = tests_directory
        self.db_path = "tests/quality_assurance/test_quality_history.db"
        self.quality_standards = {
            'min_documentation_coverage': 90.0,
            'max_slow_test_percentage': 10.0,
            'max_flaky_test_percentage': 2.0,
            'min_phi_compliance': 100.0,
            'min_marker_coverage': 95.0,
            'max_test_execution_time': 30.0,  # seconds
            'min_docstring_length': 50,
            'required_docstring_sections': [
                'test', 'verify', 'validate',  # Purpose
                'scenario', 'behavior', 'expected'  # Structure
            ]
        }
        self.initialize_database()
    
    def initialize_database(self):
        """Initialize the test quality history database."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quality_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    total_tests INTEGER NOT NULL,
                    test_reliability_score REAL NOT NULL,
                    documentation_quality_score REAL NOT NULL,
                    maintainability_score REAL NOT NULL,
                    performance_score REAL NOT NULL,
                    compliance_score REAL NOT NULL,
                    overall_quality_score REAL NOT NULL,
                    tests_with_docstrings INTEGER NOT NULL,
                    tests_with_comprehensive_docs INTEGER NOT NULL,
                    slow_tests_count INTEGER NOT NULL,
                    flaky_tests_count INTEGER NOT NULL,
                    phi_compliant_tests INTEGER NOT NULL,
                    properly_marked_tests INTEGER NOT NULL,
                    quality_issues TEXT NOT NULL,  -- JSON
                    recommendations TEXT NOT NULL  -- JSON
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS test_execution_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    test_name TEXT NOT NULL,
                    execution_time REAL NOT NULL,
                    status TEXT NOT NULL,  -- 'passed', 'failed', 'skipped'
                    file_path TEXT NOT NULL
                )
            """)
    
    def analyze_test_suite_quality(self) -> TestQualityMetrics:
        """Perform comprehensive test suite quality analysis."""
        print("Analyzing test suite quality...")
        
        # Collect all test files
        test_files = self._collect_test_files()
        
        # Analyze each test file
        file_analyses = []
        for test_file in test_files:
            analysis = self._analyze_test_file(test_file)
            if analysis:
                file_analyses.append(analysis)
        
        # Run test execution analysis
        execution_metrics = self._analyze_test_execution()
        
        # Calculate overall metrics
        metrics = self._calculate_quality_metrics(file_analyses, execution_metrics)
        
        # Store metrics
        self._store_quality_metrics(metrics)
        
        return metrics
    
    def _collect_test_files(self) -> List[str]:
        """Collect all test files for analysis."""
        test_files = []
        
        for root, dirs, files in os.walk(self.tests_directory):
            # Skip utility directories and integration scripts
            if any(skip_dir in root for skip_dir in ['utils', '__pycache__', '.pytest_cache']):
                continue
            
            for file in files:
                if file.startswith('test_') and file.endswith('.py'):
                    test_files.append(os.path.join(root, file))
        
        return test_files
    
    def _analyze_test_file(self, file_path: str) -> Optional[TestFileAnalysis]:
        """Analyze a single test file for quality metrics."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
        except (SyntaxError, UnicodeDecodeError) as e:
            return TestFileAnalysis(
                file_path=file_path,
                total_methods=0,
                documented_methods=0,
                comprehensive_docs=0,
                proper_naming=0,
                proper_markers=0,
                phi_compliant=0,
                performance_issues=[f"Syntax error: {e}"],
                quality_issues=[f"File parsing failed: {e}"],
                maintainability_score=0.0
            )
        
        # Analyze test methods
        test_methods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
                test_methods.append(node)
        
        if not test_methods:
            return None
        
        # Analyze each method
        documented_methods = 0
        comprehensive_docs = 0
        proper_naming = 0
        proper_markers = 0
        phi_compliant = 0
        performance_issues = []
        quality_issues = []
        
        for method in test_methods:
            # Check documentation
            docstring = ast.get_docstring(method)
            if docstring:
                documented_methods += 1
                if self._is_comprehensive_docstring(docstring):
                    comprehensive_docs += 1
            else:
                quality_issues.append(f"Method {method.name} missing docstring")
            
            # Check naming convention
            if self._has_proper_naming(method.name):
                proper_naming += 1
            else:
                quality_issues.append(f"Method {method.name} has poor naming")
            
            # Check for proper markers
            if self._has_proper_markers(method):
                proper_markers += 1
            else:
                quality_issues.append(f"Method {method.name} missing proper pytest markers")
            
            # Check PHI compliance
            if self._is_phi_compliant(method, content):
                phi_compliant += 1
            else:
                quality_issues.append(f"Method {method.name} may have PHI compliance issues")
        
        # Calculate maintainability score
        maintainability_score = self._calculate_maintainability_score(
            len(test_methods), documented_methods, comprehensive_docs,
            proper_naming, proper_markers, len(quality_issues)
        )
        
        return TestFileAnalysis(
            file_path=file_path,
            total_methods=len(test_methods),
            documented_methods=documented_methods,
            comprehensive_docs=comprehensive_docs,
            proper_naming=proper_naming,
            proper_markers=proper_markers,
            phi_compliant=phi_compliant,
            performance_issues=performance_issues,
            quality_issues=quality_issues,
            maintainability_score=maintainability_score
        )
    
    def _is_comprehensive_docstring(self, docstring: str) -> bool:
        """Check if docstring is comprehensive."""
        if not docstring or len(docstring.strip()) < self.quality_standards['min_docstring_length']:
            return False
        
        docstring_lower = docstring.lower()
        required_sections = self.quality_standards['required_docstring_sections']
        
        # Check for required sections
        sections_found = sum(1 for section in required_sections if section in docstring_lower)
        return sections_found >= len(required_sections) // 2  # At least half the sections
    
    def _has_proper_naming(self, method_name: str) -> bool:
        """Check if method has proper naming convention."""
        # Should start with test_ and be descriptive
        if not method_name.startswith('test_'):
            return False
        
        # Should be descriptive (more than just test_something)
        parts = method_name.split('_')
        if len(parts) < 3:  # test_verb_object minimum
            return False
        
        # Should not have generic names
        generic_names = ['test', 'basic', 'simple', 'general', 'misc']
        return not any(generic in method_name.lower() for generic in generic_names)
    
    def _has_proper_markers(self, method_node: ast.FunctionDef) -> bool:
        """Check if method has proper pytest markers."""
        # Look for pytest markers in decorators
        markers = []
        for decorator in method_node.decorator_list:
            if isinstance(decorator, ast.Attribute):
                if (isinstance(decorator.value, ast.Attribute) and 
                    decorator.value.attr == 'mark'):
                    markers.append(decorator.attr)
            elif isinstance(decorator, ast.Call):
                if (isinstance(decorator.func, ast.Attribute) and
                    isinstance(decorator.func.value, ast.Attribute) and
                    decorator.func.value.attr == 'mark'):
                    markers.append(decorator.func.attr)
        
        # Should have at least one category marker
        category_markers = ['unit', 'integration', 'performance', 'security']
        return any(marker in category_markers for marker in markers)
    
    def _is_phi_compliant(self, method_node: ast.FunctionDef, file_content: str) -> bool:
        """Check if method is PHI compliant."""
        # Get method source code
        method_start = method_node.lineno
        method_end = method_node.end_lineno if hasattr(method_node, 'end_lineno') else method_start + 20
        
        lines = file_content.split('\n')
        method_content = '\n'.join(lines[method_start-1:method_end])
        
        # Check for PHI compliance indicators
        phi_indicators = [
            'SYNTH_', 'TEST_', 'DataGenerator', 'synthetic',
            'phi_compliance', 'generate_patient'
        ]
        
        # Check for potential PHI violations
        phi_violations = [
            r'\b\d{3}-\d{2}-\d{4}\b',  # SSN pattern
            r'\b\d{10}\b',  # Phone number pattern
            r'[A-Za-z]+\s+[A-Za-z]+\s+\d+\s+[A-Za-z]+',  # Address pattern
            r'john|jane|smith|doe',  # Common real names (case insensitive)
        ]
        
        method_lower = method_content.lower()
        
        # Has PHI compliance indicators
        has_indicators = any(indicator.lower() in method_lower for indicator in phi_indicators)
        
        # No PHI violations
        has_violations = any(re.search(pattern, method_lower) for pattern in phi_violations)
        
        return has_indicators or not has_violations
    
    def _calculate_maintainability_score(self, total_methods: int, documented: int,
                                       comprehensive: int, proper_naming: int,
                                       proper_markers: int, issues_count: int) -> float:
        """Calculate maintainability score for a test file."""
        if total_methods == 0:
            return 0.0
        
        # Component scores
        doc_score = (documented / total_methods) * 100
        comprehensive_score = (comprehensive / total_methods) * 100
        naming_score = (proper_naming / total_methods) * 100
        marker_score = (proper_markers / total_methods) * 100
        
        # Issue penalty
        issue_penalty = min(issues_count * 5, 50)  # Max 50 point penalty
        
        # Weighted average
        maintainability = (
            doc_score * 0.3 +
            comprehensive_score * 0.25 +
            naming_score * 0.2 +
            marker_score * 0.25
        ) - issue_penalty
        
        return max(0.0, min(100.0, maintainability))
    
    def _analyze_test_execution(self) -> Dict:
        """Analyze test execution performance and reliability."""
        print("Analyzing test execution metrics...")
        
        # Run tests with detailed timing
        cmd = [
            "python", "-m", "pytest", "tests/",
            "--durations=0",
            "--tb=no",
            "-v",
            "--quiet"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            execution_output = result.stdout
        except subprocess.TimeoutExpired:
            return {
                'slow_tests': [],
                'failed_tests': [],
                'total_execution_time': 600.0,
                'reliability_issues': ['Test execution timed out']
            }
        
        # Parse execution results
        slow_tests = self._parse_slow_tests(execution_output)
        failed_tests = self._parse_failed_tests(execution_output)
        total_time = self._parse_total_execution_time(execution_output)
        
        return {
            'slow_tests': slow_tests,
            'failed_tests': failed_tests,
            'total_execution_time': total_time,
            'reliability_issues': []
        }
    
    def _parse_slow_tests(self, output: str) -> List[Tuple[str, float]]:
        """Parse slow tests from pytest output."""
        slow_tests = []
        
        # Look for duration information
        duration_pattern = r'(\d+\.\d+)s\s+.*?::(test_\w+)'
        matches = re.findall(duration_pattern, output)
        
        for duration_str, test_name in matches:
            duration = float(duration_str)
            if duration > self.quality_standards['max_test_execution_time']:
                slow_tests.append((test_name, duration))
        
        return slow_tests
    
    def _parse_failed_tests(self, output: str) -> List[str]:
        """Parse failed tests from pytest output."""
        failed_tests = []
        
        # Look for FAILED indicators
        failed_pattern = r'FAILED\s+.*?::(test_\w+)'
        matches = re.findall(failed_pattern, output)
        
        return matches
    
    def _parse_total_execution_time(self, output: str) -> float:
        """Parse total execution time from pytest output."""
        # Look for total time at end of output
        time_pattern = r'=+\s*(\d+\.\d+)\s*seconds?\s*=+'
        match = re.search(time_pattern, output)
        
        if match:
            return float(match.group(1))
        
        return 0.0
    
    def _calculate_quality_metrics(self, file_analyses: List[TestFileAnalysis],
                                 execution_metrics: Dict) -> TestQualityMetrics:
        """Calculate overall quality metrics."""
        if not file_analyses:
            return TestQualityMetrics(
                timestamp=datetime.now().isoformat(),
                total_tests=0,
                test_reliability_score=0.0,
                documentation_quality_score=0.0,
                maintainability_score=0.0,
                performance_score=0.0,
                compliance_score=0.0,
                overall_quality_score=0.0,
                tests_with_docstrings=0,
                tests_with_comprehensive_docs=0,
                slow_tests_count=0,
                flaky_tests_count=0,
                phi_compliant_tests=0,
                properly_marked_tests=0,
                quality_issues=[],
                recommendations=[]
            )
        
        # Aggregate metrics
        total_tests = sum(analysis.total_methods for analysis in file_analyses)
        total_documented = sum(analysis.documented_methods for analysis in file_analyses)
        total_comprehensive = sum(analysis.comprehensive_docs for analysis in file_analyses)
        total_phi_compliant = sum(analysis.phi_compliant for analysis in file_analyses)
        total_properly_marked = sum(analysis.proper_markers for analysis in file_analyses)
        
        # Calculate scores
        documentation_score = (total_documented / total_tests * 100) if total_tests > 0 else 0
        comprehensive_doc_score = (total_comprehensive / total_tests * 100) if total_tests > 0 else 0
        compliance_score = (total_phi_compliant / total_tests * 100) if total_tests > 0 else 0
        marker_score = (total_properly_marked / total_tests * 100) if total_tests > 0 else 0
        
        # Performance metrics
        slow_tests = execution_metrics.get('slow_tests', [])
        failed_tests = execution_metrics.get('failed_tests', [])
        
        performance_score = max(0, 100 - (len(slow_tests) / total_tests * 100)) if total_tests > 0 else 100
        reliability_score = max(0, 100 - (len(failed_tests) / total_tests * 100)) if total_tests > 0 else 100
        
        # Maintainability score (average of file scores)
        maintainability_score = sum(analysis.maintainability_score for analysis in file_analyses) / len(file_analyses)
        
        # Overall quality score (weighted average)
        overall_score = (
            documentation_score * 0.2 +
            comprehensive_doc_score * 0.15 +
            maintainability_score * 0.2 +
            performance_score * 0.15 +
            reliability_score * 0.15 +
            compliance_score * 0.15
        )
        
        # Collect quality issues and recommendations
        quality_issues = []
        recommendations = []
        
        for analysis in file_analyses:
            quality_issues.extend(analysis.quality_issues)
        
        # Generate recommendations
        if documentation_score < self.quality_standards['min_documentation_coverage']:
            recommendations.append(f"Improve test documentation coverage (current: {documentation_score:.1f}%)")
        
        if len(slow_tests) > 0:
            recommendations.append(f"Optimize {len(slow_tests)} slow tests or mark them appropriately")
        
        if compliance_score < self.quality_standards['min_phi_compliance']:
            recommendations.append("Review and improve PHI compliance in test data")
        
        if marker_score < self.quality_standards['min_marker_coverage']:
            recommendations.append("Add proper pytest markers to test methods")
        
        return TestQualityMetrics(
            timestamp=datetime.now().isoformat(),
            total_tests=total_tests,
            test_reliability_score=reliability_score,
            documentation_quality_score=(documentation_score + comprehensive_doc_score) / 2,
            maintainability_score=maintainability_score,
            performance_score=performance_score,
            compliance_score=compliance_score,
            overall_quality_score=overall_score,
            tests_with_docstrings=total_documented,
            tests_with_comprehensive_docs=total_comprehensive,
            slow_tests_count=len(slow_tests),
            flaky_tests_count=len(failed_tests),  # Simplified - failed tests as proxy for flaky
            phi_compliant_tests=total_phi_compliant,
            properly_marked_tests=total_properly_marked,
            quality_issues=quality_issues[:50],  # Limit to top 50 issues
            recommendations=recommendations
        )
    
    def _store_quality_metrics(self, metrics: TestQualityMetrics):
        """Store quality metrics in the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO quality_history (
                    timestamp, total_tests, test_reliability_score,
                    documentation_quality_score, maintainability_score,
                    performance_score, compliance_score, overall_quality_score,
                    tests_with_docstrings, tests_with_comprehensive_docs,
                    slow_tests_count, flaky_tests_count, phi_compliant_tests,
                    properly_marked_tests, quality_issues, recommendations
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metrics.timestamp,
                metrics.total_tests,
                metrics.test_reliability_score,
                metrics.documentation_quality_score,
                metrics.maintainability_score,
                metrics.performance_score,
                metrics.compliance_score,
                metrics.overall_quality_score,
                metrics.tests_with_docstrings,
                metrics.tests_with_comprehensive_docs,
                metrics.slow_tests_count,
                metrics.flaky_tests_count,
                metrics.phi_compliant_tests,
                metrics.properly_marked_tests,
                json.dumps(metrics.quality_issues),
                json.dumps(metrics.recommendations)
            ))
    
    def generate_quality_report(self, metrics: TestQualityMetrics) -> str:
        """Generate comprehensive quality report."""
        report_lines = [
            "# Test Suite Quality Report",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Overall Quality Score",
            f"**{metrics.overall_quality_score:.1f}/100**",
            "",
            "## Quality Dimensions",
            f"- **Test Reliability**: {metrics.test_reliability_score:.1f}/100",
            f"- **Documentation Quality**: {metrics.documentation_quality_score:.1f}/100",
            f"- **Maintainability**: {metrics.maintainability_score:.1f}/100",
            f"- **Performance**: {metrics.performance_score:.1f}/100",
            f"- **Compliance**: {metrics.compliance_score:.1f}/100",
            "",
            "## Test Suite Statistics",
            f"- **Total Tests**: {metrics.total_tests:,}",
            f"- **Tests with Docstrings**: {metrics.tests_with_docstrings:,} ({metrics.tests_with_docstrings/metrics.total_tests*100:.1f}%)",
            f"- **Comprehensive Documentation**: {metrics.tests_with_comprehensive_docs:,} ({metrics.tests_with_comprehensive_docs/metrics.total_tests*100:.1f}%)",
            f"- **PHI Compliant Tests**: {metrics.phi_compliant_tests:,} ({metrics.phi_compliant_tests/metrics.total_tests*100:.1f}%)",
            f"- **Properly Marked Tests**: {metrics.properly_marked_tests:,} ({metrics.properly_marked_tests/metrics.total_tests*100:.1f}%)",
            "",
            "## Performance Issues",
            f"- **Slow Tests**: {metrics.slow_tests_count} (>{self.quality_standards['max_test_execution_time']}s)",
            f"- **Flaky Tests**: {metrics.flaky_tests_count}",
            "",
        ]
        
        # Quality issues section
        if metrics.quality_issues:
            report_lines.extend([
                "## Quality Issues",
                ""
            ])
            
            # Group issues by type
            issue_groups = {}
            for issue in metrics.quality_issues[:20]:  # Top 20 issues
                issue_type = issue.split()[0] if issue else "General"
                if issue_type not in issue_groups:
                    issue_groups[issue_type] = []
                issue_groups[issue_type].append(issue)
            
            for issue_type, issues in issue_groups.items():
                report_lines.append(f"### {issue_type} Issues")
                for issue in issues[:5]:  # Top 5 per type
                    report_lines.append(f"- {issue}")
                report_lines.append("")
        
        # Recommendations section
        if metrics.recommendations:
            report_lines.extend([
                "## Recommendations",
                ""
            ])
            
            for i, recommendation in enumerate(metrics.recommendations, 1):
                report_lines.append(f"{i}. {recommendation}")
            
            report_lines.append("")
        
        # Quality standards comparison
        report_lines.extend([
            "## Quality Standards Compliance",
            ""
        ])
        
        standards_check = [
            ("Documentation Coverage", metrics.tests_with_docstrings/metrics.total_tests*100, self.quality_standards['min_documentation_coverage']),
            ("PHI Compliance", metrics.phi_compliant_tests/metrics.total_tests*100, self.quality_standards['min_phi_compliance']),
            ("Marker Coverage", metrics.properly_marked_tests/metrics.total_tests*100, self.quality_standards['min_marker_coverage']),
            ("Slow Test Percentage", metrics.slow_tests_count/metrics.total_tests*100, self.quality_standards['max_slow_test_percentage']),
        ]
        
        for standard_name, current_value, threshold in standards_check:
            if standard_name.endswith("Percentage") and current_value <= threshold:
                status = "✅"
            elif not standard_name.endswith("Percentage") and current_value >= threshold:
                status = "✅"
            else:
                status = "❌"
            
            report_lines.append(f"- {status} **{standard_name}**: {current_value:.1f}% (threshold: {threshold:.1f}%)")
        
        return "\n".join(report_lines)


def main():
    """Main function for running test quality analysis."""
    analyzer = TestQualityAnalyzer()
    
    # Run quality analysis
    metrics = analyzer.analyze_test_suite_quality()
    
    # Generate report
    report = analyzer.generate_quality_report(metrics)
    
    # Save report
    report_path = f"tests/quality_assurance/quality_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    
    print(f"Test quality analysis complete. Report saved to {report_path}")
    print(f"\nQuality Summary:")
    print(f"Overall Quality Score: {metrics.overall_quality_score:.1f}/100")
    print(f"Total Tests: {metrics.total_tests:,}")
    print(f"Documentation Coverage: {metrics.tests_with_docstrings/metrics.total_tests*100:.1f}%")
    print(f"PHI Compliance: {metrics.phi_compliant_tests/metrics.total_tests*100:.1f}%")
    
    if metrics.recommendations:
        print(f"\nTop Recommendations:")
        for i, rec in enumerate(metrics.recommendations[:3], 1):
            print(f"{i}. {rec}")
    
    # Return exit code based on quality score
    return 0 if metrics.overall_quality_score >= 80.0 else 1


if __name__ == "__main__":
    exit(main())