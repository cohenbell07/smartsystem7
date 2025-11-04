"""
Approval gate service for risky agent actions.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
from sqlmodel import Session, select
from app.models import Approval, ApprovalStatus
from app.database import engine

logger = logging.getLogger(__name__)


class ApprovalService:
    """Manages approval gates for agent actions."""

    def __init__(self):
        pass

    async def request_approval(
        self,
        run_id: int,
        step_id: str,
        action: str,
        risk_level: str = "medium",
        details: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Request approval for an action.

        Args:
            run_id: Run ID
            step_id: Step identifier
            action: Description of action requiring approval
            risk_level: "low", "medium", or "high"
            details: Additional context

        Returns:
            Approval ID
        """
        logger.info(f"Requesting approval for run {run_id}, step {step_id}")

        with Session(engine) as session:
            approval = Approval(
                run_id=run_id,
                step_id=step_id,
                action=action,
                risk_level=risk_level,
                details=details or {},
                status=ApprovalStatus.PENDING,
            )

            session.add(approval)
            session.commit()
            session.refresh(approval)

            logger.info(f"Created approval request {approval.id}")
            return approval.id

    async def check_approval(self, approval_id: int, timeout: int = 300) -> bool:
        """
        Check if approval has been granted (blocking).

        Args:
            approval_id: Approval ID
            timeout: Max wait time in seconds

        Returns:
            True if approved, False if rejected or timeout
        """
        import asyncio

        logger.info(f"Checking approval {approval_id}")

        start_time = datetime.utcnow()
        max_wait = timeout

        while True:
            with Session(engine) as session:
                approval = session.get(Approval, approval_id)

                if not approval:
                    logger.error(f"Approval {approval_id} not found")
                    return False

                if approval.status == ApprovalStatus.APPROVED:
                    logger.info(f"Approval {approval_id} granted")
                    return True

                if approval.status == ApprovalStatus.REJECTED:
                    logger.info(f"Approval {approval_id} rejected")
                    return False

                # Check timeout
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                if elapsed > max_wait:
                    logger.warning(f"Approval {approval_id} timed out after {elapsed}s")
                    return False

            # Wait before checking again
            await asyncio.sleep(2)

    async def approve(self, approval_id: int, approved_by: str = "user") -> bool:
        """
        Approve an action.

        Args:
            approval_id: Approval ID
            approved_by: User who approved

        Returns:
            True if successful
        """
        logger.info(f"Approving {approval_id}")

        with Session(engine) as session:
            approval = session.get(Approval, approval_id)

            if not approval:
                logger.error(f"Approval {approval_id} not found")
                return False

            approval.status = ApprovalStatus.APPROVED
            approval.approved_by = approved_by
            approval.approved_at = datetime.utcnow()

            session.add(approval)
            session.commit()

            logger.info(f"Approval {approval_id} granted by {approved_by}")
            return True

    async def reject(self, approval_id: int, approved_by: str = "user") -> bool:
        """
        Reject an action.

        Args:
            approval_id: Approval ID
            approved_by: User who rejected

        Returns:
            True if successful
        """
        logger.info(f"Rejecting {approval_id}")

        with Session(engine) as session:
            approval = session.get(Approval, approval_id)

            if not approval:
                logger.error(f"Approval {approval_id} not found")
                return False

            approval.status = ApprovalStatus.REJECTED
            approval.approved_by = approved_by
            approval.approved_at = datetime.utcnow()

            session.add(approval)
            session.commit()

            logger.info(f"Approval {approval_id} rejected by {approved_by}")
            return True

    async def get_pending_approvals(self, run_id: int) -> list[Approval]:
        """
        Get all pending approvals for a run.

        Args:
            run_id: Run ID

        Returns:
            List of pending approvals
        """
        with Session(engine) as session:
            statement = select(Approval).where(
                Approval.run_id == run_id,
                Approval.status == ApprovalStatus.PENDING
            )
            approvals = session.exec(statement).all()

            return list(approvals)
