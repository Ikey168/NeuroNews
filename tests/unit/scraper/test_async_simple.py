import pytest
import asyncio

@pytest.mark.asyncio
async def test_simple_async():
    """Test simple async functionality."""
    await asyncio.sleep(0.01)
    assert True

def test_simple_sync():
    """Test simple sync functionality.""" 
    assert True
