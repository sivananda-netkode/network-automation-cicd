"""Sequential Multi-Environment Deployment Pipeline Runner.

Executes the complete deployment lifecycle in sequence:
  1. CI Validation & Automated Testing (Automatic)
  2. Deploy Staging Configuration (Hyderabad Netkode) (Automatic)
  3. Verify Staging Health & Operations (Automatic)
  4. Production Deployment (Vizag Netkode) (You approve once)
  5. Verify Production Health & Operations (Automatic)
"""

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from src.network.deployment_engine import run_deployment
from src.network.operational_validation import run_validation


def run_ci_validation() -> bool:
    """Execute CI validation test suite automatically."""
    print("\n>>> [STEP 1/5] RUNNING CI VALIDATION (Automatic)...")
    exit_code = pytest.main(["-q", "--tb=line", "tests/"])
    if exit_code != 0:
        print("\n❌ CRITICAL: CI validation failed! Aborting pipeline.")
        print("⛔ Neither Staging nor Production will be touched.")
        return False
    print("✔ CI validation passed successfully (100%).")
    return True


def run_pipeline(auto_approve: bool = False, mode: str = "incremental", skip_ci: bool = False) -> bool:
    """Execute CI validation, Staging deployment & verification, Toll Gate, and Production."""
    start_total = time.time()

    print("\n" + "=" * 70)
    print("      NETWORK CI/CD PIPELINE: STAGING -> PRODUCTION")
    print("=" * 70)

    # -------------------------------------------------------------
    # STAGE 1: CI VALIDATION (Automatic)
    # -------------------------------------------------------------
    if not skip_ci:
        if not run_ci_validation():
            return False
    else:
        print("\n>>> [STEP 1/5] CI VALIDATION: Skipped via --skip-ci flag.")

    # -------------------------------------------------------------
    # STAGE 2: STAGING DEPLOYMENT (Automatic)
    # -------------------------------------------------------------
    print("\n>>> [STEP 2/5] DEPLOYING TO STAGING (Hyderabad Netkode) (Automatic)...")
    staging_deploy_ok = run_deployment(
        environment="staging",
        mode=mode,
        auto_approve=True,  # Staging deployment is automatic
    )

    if not staging_deploy_ok:
        print("\n❌ CRITICAL: Staging deployment failed! Aborting pipeline.")
        print("⛔ Production environment will NOT be touched.")
        return False

    print("✔ Staging deployment completed successfully.")

    # -------------------------------------------------------------
    # STAGE 3: STAGING OPERATIONAL VERIFICATION (Automatic)
    # -------------------------------------------------------------
    print("\n>>> [STEP 3/5] VERIFYING STAGING HEALTH & OPERATIONS (Automatic)...")
    staging_verify_ok = run_validation(environment="staging")

    if not staging_verify_ok:
        print("\n❌ CRITICAL: Staging health checks failed! Aborting pipeline.")
        print("⛔ Production deployment blocked due to staging verification failure.")
        return False

    print("✔ Staging health & operational verification passed (100%).")

    # -------------------------------------------------------------
    # STAGE 4: PRODUCTION DEPLOYMENT (You approve once)
    # -------------------------------------------------------------
    print("\n" + "-" * 70)
    print("✔ STAGING SUCCESS CONFIRMED: All staging checks passed.")
    print("TOLL GATE: Ready for PRODUCTION deployment (Vizag Netkode).")
    print("-" * 70)

    if not auto_approve:
        try:
            choice = input("\nType DEPLOY to approve Production deployment: ").strip()
            if choice != "DEPLOY":
                print("\n⛔ Production deployment cancelled by user.")
                return False
        except EOFError:
            print("\nNon-interactive session without --auto-approve. Aborting.")
            return False

    print("\n>>> [STEP 4/5] DEPLOYING TO PRODUCTION (Vizag Netkode)...")
    prod_deploy_ok = run_deployment(
        environment="production",
        mode=mode,
        auto_approve=True,  # Approved via the toll gate above
    )

    if not prod_deploy_ok:
        print("\n❌ CRITICAL: Production deployment encountered errors.")
        return False

    print("✔ Production deployment completed successfully.")

    # -------------------------------------------------------------
    # STAGE 5: PRODUCTION OPERATIONAL VERIFICATION (Automatic)
    # -------------------------------------------------------------
    print("\n>>> [STEP 5/5] VERIFYING PRODUCTION HEALTH & OPERATIONS (Automatic)...")
    prod_verify_ok = run_validation(environment="production")

    if not prod_verify_ok:
        print("\n❌ WARNING: Production post-deployment health check reported issues.")
        return False

    print("✔ Production health & operational verification passed (100%).")

    duration = round(time.time() - start_total, 2)
    print("\n" + "=" * 70)
    print(f"🎉 PIPELINE COMPLETED SUCCESSFULLY IN {duration}s")
    print("Both Staging and Production environments are 100% in sync and verified.")
    print("=" * 70 + "\n")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Sequential Multi-Environment Network Deployment Pipeline"
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Automatically proceed to Production without interactive Toll Gate prompt",
    )
    parser.add_argument(
        "--skip-ci",
        action="store_true",
        help="Skip CI validation tests and proceed directly to deployments",
    )
    parser.add_argument(
        "--mode",
        choices=["incremental", "full"],
        default="incremental",
        help="Deployment mode: 'incremental' (default) or 'full'",
    )

    args = parser.parse_args()
    success = run_pipeline(auto_approve=args.auto_approve, mode=args.mode, skip_ci=args.skip_ci)
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

