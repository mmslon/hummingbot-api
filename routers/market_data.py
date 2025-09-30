import asyncio
import time

from fastapi import APIRouter, Request, HTTPException, Depends
from hummingbot.data_feed.candles_feed.data_types import HistoricalCandlesConfig, CandlesConfig
from hummingbot.data_feed.candles_feed.candles_factory import CandlesFactory

from models.market_data import CandlesConfigRequest
from services.market_data_feed_manager import MarketDataFeedManager
from models import (
    PriceRequest,
    PricesResponse,
    FundingInfoRequest,
    FundingInfoResponse,
    OrderBookRequest,
    OrderBookResponse,
    OrderBookLevel,
    VolumeForPriceRequest,
    PriceForVolumeRequest,
    QuoteVolumeForPriceRequest,
    PriceForQuoteVolumeRequest,
    VWAPForVolumeRequest,
    OrderBookQueryResult,
)
from deps import get_market_data_feed_manager

router = APIRouter(tags=["Market Data"], prefix="/market-data")


@router.post("/candles")
async def get_candles(request: Request, candles_config: CandlesConfigRequest):
    """
    Get real-time candles data for a specific trading pair.

    This endpoint uses the MarketDataProvider to get or create a candles feed that will
    automatically start and maintain real-time updates. Subsequent requests with the same
    configuration will reuse the existing feed for up-to-date data.

    Args:
        request: FastAPI request object
        candles_config: Configuration for the candles including connector, trading_pair, interval, and max_records

    Returns:
        Real-time candles data or error message
    """
    try:
        market_data_feed_manager: MarketDataFeedManager = request.app.state.market_data_feed_manager

        # Get or create the candles feed (this will start it automatically and track access time)
        candles_cfg = CandlesConfig(
            connector=candles_config.connector_name,
            trading_pair=candles_config.trading_pair,
            interval=candles_config.interval,
            max_records=candles_config.max_records,
        )
        candles_feed = market_data_feed_manager.get_candles_feed(candles_cfg)

        # Wait for the candles feed to be ready
        while not candles_feed.ready:
            await asyncio.sleep(0.1)

        # Get the candles dataframe
        df = candles_feed.candles_df

        if df is not None and not df.empty:
            # Limit to requested max_records and remove duplicates
            df = df.tail(candles_config.max_records)
            df = df.drop_duplicates(subset=["timestamp"], keep="last")
            # Convert to dict for JSON serialization
            return df.to_dict(orient="records")
        else:
            return {"error": "No candles data available"}

    except Exception as e:
        return {"error": str(e)}


@router.post("/historical-candles")
async def get_historical_candles(request: Request, config: HistoricalCandlesConfig):
    """
    Get historical candles data for a specific trading pair.

    Args:
        config: Configuration for historical candles including connector, trading pair, interval, start and end time

    Returns:
        Historical candles data or error message
    """
    try:
        updated_config = config

        if config.connector_name == "bitmart":
            updated_config.end_time = time.time()
            updated_config.start_time = 1758653042
            updated_config.trading_pair = config.trading_pair.replace("-USDT", "_USDT")
            updated_config.interval = "1h"

        market_data_feed_manager: MarketDataFeedManager = request.app.state.market_data_feed_manager

        # Create candles config from historical config
        candles_config = CandlesConfig(
            connector=updated_config.connector_name, trading_pair=updated_config.trading_pair, interval=updated_config.interval
        )

        # Get or create the candles feed (this will track access time)
        candles = market_data_feed_manager.get_candles_feed(candles_config)

        # Fetch historical candles
        historical_data = await candles.get_historical_candles(config=updated_config)

        if historical_data is not None and not historical_data.empty:
            # Convert to dict for JSON serialization
            return historical_data.to_dict(orient="records")
        else:
            return {"error": "No historical data available"}

    except Exception as e:
        return {"error": str(e)}


@router.get("/active-feeds")
async def get_active_feeds(request: Request):
    """
    Get information about currently active market data feeds.

    Args:
        request: FastAPI request object to access application state

    Returns:
        Dictionary with active feeds information including last access times and expiration
    """
    try:
        market_data_feed_manager: MarketDataFeedManager = request.app.state.market_data_feed_manager
        return market_data_feed_manager.get_active_feeds_info()
    except Exception as e:
        return {"error": str(e)}


@router.get("/settings")
async def get_market_data_settings():
    """
    Get current market data settings for debugging.

    Returns:
        Dictionary with current market data configuration including cleanup and timeout settings
    """
    from config import settings

    return {
        "cleanup_interval": settings.market_data.cleanup_interval,
        "feed_timeout": settings.market_data.feed_timeout,
        "description": "cleanup_interval: seconds between cleanup runs, feed_timeout: seconds before unused feeds expire",
    }


@router.get("/available-candle-connectors")
async def get_available_candle_connectors():
    """
    Get list of available connectors that support candle data feeds.

    Returns:
        List of connector names that can be used for fetching candle data
    """
    return list(CandlesFactory._candles_map.keys())


# Enhanced Market Data Endpoints


@router.post("/prices", response_model=PricesResponse)
async def get_prices(request: PriceRequest, market_data_manager: MarketDataFeedManager = Depends(get_market_data_feed_manager)):
    """
    Get current prices for specified trading pairs from a connector.

    Args:
        request: Price request with connector name and trading pairs
        market_data_manager: Injected market data feed manager

    Returns:
        Current prices for the specified trading pairs

    Raises:
        HTTPException: 500 if there's an error fetching prices
    """
    try:
        prices = await market_data_manager.get_prices(request.connector_name, request.trading_pairs)

        if "error" in prices:
            raise HTTPException(status_code=500, detail=prices["error"])

        return PricesResponse(connector=request.connector_name, prices=prices, timestamp=time.time())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching prices: {str(e)}")


@router.post("/funding-info", response_model=FundingInfoResponse)
async def get_funding_info(
    request: FundingInfoRequest, market_data_manager: MarketDataFeedManager = Depends(get_market_data_feed_manager)
):
    """
    Get funding information for a perpetual trading pair.

    Args:
        request: Funding info request with connector name and trading pair
        market_data_manager: Injected market data feed manager

    Returns:
        Funding information including rates, timestamps, and prices

    Raises:
        HTTPException: 400 for non-perpetual connectors, 500 for other errors
    """
    try:
        if "_perpetual" not in request.connector_name.lower():
            raise HTTPException(status_code=400, detail="Funding info is only available for perpetual trading pairs.")
        funding_info = await market_data_manager.get_funding_info(request.connector_name, request.trading_pair)

        if "error" in funding_info:
            if "not supported" in funding_info["error"]:
                raise HTTPException(status_code=400, detail=funding_info["error"])
            else:
                raise HTTPException(status_code=500, detail=funding_info["error"])

        return FundingInfoResponse(**funding_info)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching funding info: {str(e)}")


@router.post("/order-book", response_model=OrderBookResponse)
async def get_order_book(
    request: OrderBookRequest, market_data_manager: MarketDataFeedManager = Depends(get_market_data_feed_manager)
):
    """
    Get order book snapshot with specified depth.

    Args:
        request: Order book request with connector, trading pair, and depth
        market_data_manager: Injected market data feed manager

    Returns:
        Order book snapshot with bids and asks

    Raises:
        HTTPException: 500 if there's an error fetching order book
    """
    try:
        order_book_data = await market_data_manager.get_order_book_data(
            request.connector_name, request.trading_pair, request.depth
        )

        if "error" in order_book_data:
            raise HTTPException(status_code=500, detail=order_book_data["error"])

        # Convert to response format - data comes as [price, amount] lists
        bids = [OrderBookLevel(price=bid[0], amount=bid[1]) for bid in order_book_data["bids"]]
        asks = [OrderBookLevel(price=ask[0], amount=ask[1]) for ask in order_book_data["asks"]]

        return OrderBookResponse(
            trading_pair=order_book_data["trading_pair"], bids=bids, asks=asks, timestamp=order_book_data["timestamp"]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching order book: {str(e)}")


# Order Book Query Endpoints


@router.post("/order-book/price-for-volume", response_model=OrderBookQueryResult)
async def get_price_for_volume(
    request: PriceForVolumeRequest, market_data_manager: MarketDataFeedManager = Depends(get_market_data_feed_manager)
):
    """
    Get the price required to fill a specific volume on the order book.

    Args:
        request: Request with connector, trading pair, volume, and side
        market_data_manager: Injected market data feed manager

    Returns:
        Order book query result with price and volume information
    """
    try:
        result = await market_data_manager.get_order_book_query_result(
            request.connector_name, request.trading_pair, request.is_buy, volume=request.volume
        )

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        return OrderBookQueryResult(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in order book query: {str(e)}")


@router.post("/order-book/volume-for-price", response_model=OrderBookQueryResult)
async def get_volume_for_price(
    request: VolumeForPriceRequest, market_data_manager: MarketDataFeedManager = Depends(get_market_data_feed_manager)
):
    """
    Get the volume available at a specific price level on the order book.

    Args:
        request: Request with connector, trading pair, price, and side
        market_data_manager: Injected market data feed manager

    Returns:
        Order book query result with volume information
    """
    try:
        result = await market_data_manager.get_order_book_query_result(
            request.connector_name, request.trading_pair, request.is_buy, price=request.price
        )

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        return OrderBookQueryResult(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in order book query: {str(e)}")


@router.post("/order-book/price-for-quote-volume", response_model=OrderBookQueryResult)
async def get_price_for_quote_volume(
    request: PriceForQuoteVolumeRequest, market_data_manager: MarketDataFeedManager = Depends(get_market_data_feed_manager)
):
    """
    Get the price required to fill a specific quote volume on the order book.

    Args:
        request: Request with connector, trading pair, quote volume, and side
        market_data_manager: Injected market data feed manager

    Returns:
        Order book query result with price and volume information
    """
    try:
        result = await market_data_manager.get_order_book_query_result(
            request.connector_name, request.trading_pair, request.is_buy, quote_volume=request.quote_volume
        )

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        return OrderBookQueryResult(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in order book query: {str(e)}")


@router.post("/order-book/quote-volume-for-price", response_model=OrderBookQueryResult)
async def get_quote_volume_for_price(
    request: QuoteVolumeForPriceRequest, market_data_manager: MarketDataFeedManager = Depends(get_market_data_feed_manager)
):
    """
    Get the quote volume available at a specific price level on the order book.

    Args:
        request: Request with connector, trading pair, price, and side
        market_data_manager: Injected market data feed manager

    Returns:
        Order book query result with quote volume information
    """
    try:
        result = await market_data_manager.get_order_book_query_result(
            request.connector_name, request.trading_pair, request.is_buy, quote_price=request.price
        )

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        return OrderBookQueryResult(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in order book query: {str(e)}")


@router.post("/order-book/vwap-for-volume", response_model=OrderBookQueryResult)
async def get_vwap_for_volume(
    request: VWAPForVolumeRequest, market_data_manager: MarketDataFeedManager = Depends(get_market_data_feed_manager)
):
    """
    Get the VWAP (Volume Weighted Average Price) for a specific volume on the order book.

    Args:
        request: Request with connector, trading pair, volume, and side
        market_data_manager: Injected market data feed manager

    Returns:
        Order book query result with VWAP information
    """
    try:
        result = await market_data_manager.get_order_book_query_result(
            request.connector_name, request.trading_pair, request.is_buy, vwap_volume=request.volume
        )

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        return OrderBookQueryResult(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in order book query: {str(e)}")
