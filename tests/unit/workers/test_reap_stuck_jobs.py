"""Tests for the reap_stuck_jobs worker function."""

import time
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_reap_stuck_jobs_marks_old_running():
    """Jobs running longer than timeout should be marked as failed."""
    from nkz_soil.workers.ingest import reap_stuck_jobs

    mock_redis = AsyncMock()
    mock_redis.scan = AsyncMock(side_effect=[
        (0, ["arq:job:job1", "arq:job:job2"]),
    ])
    mock_redis.hgetall = AsyncMock(side_effect=[
        {"status": "running", "enqueue_time": str(time.monotonic() - 3600)},  # 1h old
        {"status": "pending", "enqueue_time": str(time.monotonic() - 100)},   # 100s old
    ])
    mock_redis.hset = AsyncMock()
    mock_redis.close = AsyncMock()

    ctx = {"redis": mock_redis}

    await reap_stuck_jobs(ctx)

    # Only the old running job should be reaped
    assert mock_redis.hset.call_count == 1
    mock_redis.hset.assert_called_once_with(
        "arq:job:job1",
        mapping={"status": "failed", "error": "stuck_job_timeout"},
    )


@pytest.mark.asyncio
async def test_reap_stuck_jobs_no_stuck_jobs():
    """No jobs to reap if all are recent."""
    from nkz_soil.workers.ingest import reap_stuck_jobs

    mock_redis = AsyncMock()
    mock_redis.scan = AsyncMock(return_value=(0, ["arq:job:job1"]))
    mock_redis.hgetall = AsyncMock(
        return_value={"status": "running", "enqueue_time": str(time.monotonic() - 60)}
    )
    mock_redis.hset = AsyncMock()
    mock_redis.close = AsyncMock()

    ctx = {"redis": mock_redis}

    await reap_stuck_jobs(ctx)

    assert mock_redis.hset.call_count == 0


@pytest.mark.asyncio
async def test_reap_stuck_jobs_empty_queue():
    """No jobs in queue — should complete without error."""
    from nkz_soil.workers.ingest import reap_stuck_jobs

    mock_redis = AsyncMock()
    mock_redis.scan = AsyncMock(return_value=(0, []))
    mock_redis.close = AsyncMock()

    ctx = {"redis": mock_redis}

    await reap_stuck_jobs(ctx)

    # Should not raise
    assert mock_redis.scan.call_count == 1
