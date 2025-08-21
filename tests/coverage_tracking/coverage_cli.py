#!/usr/bin/env python3
"""
Command-line interface for coverage tracking operations.

This script provides easy access to coverage tracking functionality
for the 30% coverage improvement project.
"""

import argparse
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.coverage_tracking.baseline_tracker import get_coverage_tracker
from tests.coverage_tracking.reporting import get_coverage_reporter


def establish_baseline():
    """Establish the coverage baseline."""
    print("🔍 Establishing coverage baseline...")
    tracker = get_coverage_tracker()
    snapshot = tracker.establish_baseline()
    
    print(f"✅ Baseline established:")
    print(f"   Coverage: {snapshot.overall_coverage:.2f}%")
    print(f"   Statements: {snapshot.covered_statements}/{snapshot.total_statements}")
    print(f"   Test files: {snapshot.test_files_count}")
    print(f"   Execution time: {snapshot.execution_time_seconds:.1f}s")


def measure_progress(test_file=None):
    """Measure incremental coverage progress."""
    print("📊 Measuring coverage progress...")
    tracker = get_coverage_tracker()
    snapshot, progress = tracker.measure_incremental_progress(test_file)
    
    report = tracker.generate_progress_report(progress)
    print(report)


def generate_report():
    """Generate comprehensive coverage report."""
    print("📋 Generating comprehensive coverage report...")
    reporter = get_coverage_reporter()
    report = reporter.generate_comprehensive_report()
    
    # Save reports
    json_path = reporter.save_report(report)
    md_path = reporter.save_markdown_report(report)
    
    print(f"✅ Reports generated:")
    print(f"   JSON: {json_path}")
    print(f"   Markdown: {md_path}")
    
    # Print quick summary
    print("\n" + "="*50)
    print(reporter.generate_quick_status())


def quick_status():
    """Show quick coverage status."""
    print("⚡ Quick Coverage Status:")
    reporter = get_coverage_reporter()
    status = reporter.generate_quick_status()
    print(status)


def validate_target():
    """Validate if 30% target has been reached."""
    print("🎯 Validating coverage target...")
    tracker = get_coverage_tracker()
    target_reached, validation_report = tracker.validate_target_reached()
    
    if target_reached:
        print("🎉 Congratulations! 30% coverage target has been reached!")
    else:
        print("📈 Still working toward 30% target...")
    
    print(f"Current coverage: {validation_report['current_coverage']:.2f}%")
    print(f"Target coverage: {validation_report['target_coverage']:.2f}%")
    print(f"Total improvement: +{validation_report['total_improvement']:.2f}%")
    print(f"Statements improvement: +{validation_report['statements_improvement']}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Coverage tracking CLI for 30% coverage target project"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Baseline command
    subparsers.add_parser('baseline', help='Establish coverage baseline')
    
    # Progress command
    progress_parser = subparsers.add_parser('progress', help='Measure incremental progress')
    progress_parser.add_argument('--test-file', help='Name of test file that was added')
    
    # Report command
    subparsers.add_parser('report', help='Generate comprehensive coverage report')
    
    # Status command
    subparsers.add_parser('status', help='Show quick coverage status')
    
    # Validate command
    subparsers.add_parser('validate', help='Validate if 30% target reached')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == 'baseline':
            establish_baseline()
        elif args.command == 'progress':
            measure_progress(args.test_file)
        elif args.command == 'report':
            generate_report()
        elif args.command == 'status':
            quick_status()
        elif args.command == 'validate':
            validate_target()
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()