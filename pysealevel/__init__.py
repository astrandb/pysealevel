"""
Module sealevel fetches data from Swedish Maritime Administration (Sjöfartsverket)
for use in Home Assistant
"""
import abc
import aiohttp
import copy
import json

from collections import OrderedDict
from datetime import datetime
from urllib.request import urlopen
from typing import List

__version__ = "0.0.1"
_LOGGER = logging.getLogger(__name__)

URL_BASE = (
    'https://services.viva.sjofartsverket.se:8080/output/vivaoutputservice.svc/vivastation/'
)


class SealevelException(Exception):
    pass


class SealevelData:
    """
    Get and hold data from API
    """

    def __init__(self, sealevel: int) -> None:
        """Constructor"""
        _sealevel = sealevel
        

class SealevelAPI():
    """Default implementation for api"""

    def __init__(self) -> None:
        """Init the API with or without session"""
        self.session = None

    async def async_get_data_api(self, location: str) -> {}:
        """gets data from API asyncronously"""
        api_url = URL_BASE + location

        if self.session is None:
            self.session = aiohttp.ClientSession()

        async with self.session.get(api_url) as response:
            if response.status != 200:
                raise SealevelException(
                    f"Failed to access Sealevel API - Code:  {}", response.status
                )
            data = await response.text()
            return json.loads(data)


class Smhi:
    """
    Class that use the Swedish Maritime Administration (Sjöfartsverket) semi-open API
    to get sealevel data
    """

    def __init__(
        self,
        location: str,
        session: aiohttp.ClientSession = None,
        api: SmhiAPIBase = SmhiAPI(),
    ) -> None:
        self._longitude = str(round(float(longitude), 6))
        self._latitude = str(round(float(latitude), 6))
        self._api = api

        if session:
            self._api.session = session

    def get_forecast(self) -> List[SmhiForecast]:
        """
        Returns a list of forecasts. The first in list are the current one
        """
        json_data = self._api.get_forecast_api(self._longitude, self._latitude)
        return _get_forecast(json_data)

    async def async_get_forecast(self) -> List[SmhiForecast]:
        """
        Returns a list of forecasts. The first in list are the current one
        """
        json_data = await self._api.async_get_forecast_api(
            self._longitude, self._latitude
        )
        return _get_forecast(json_data)


def _get_forecast(api_result: dict) -> List[SmhiForecast]:
    """Converts results fråm API to SmhiForeCast list"""
    forecasts = []

    # Need the ordered dict to get
    # the days in order in next stage
    forecasts_ordered = OrderedDict()

    forecasts_ordered = _get_all_forecast_from_api(api_result)

    # Used to calc the daycount
    day_nr = 1

    for day in forecasts_ordered:
        forecasts_day = forecasts_ordered[day]

        if day_nr == 1:
            # Add the most recent forecast
            forecasts.append(copy.deepcopy(forecasts_day[0]))

        total_precipitation = float(0.0)
        forecast_temp_max = -100.0
        forecast_temp_min = 100.0
        forecast = None
        for forcast_day in forecasts_day:
            temperature = forcast_day.temperature
            if forecast_temp_min > temperature:
                forecast_temp_min = temperature
            if forecast_temp_max < temperature:
                forecast_temp_max = temperature

            if forcast_day.valid_time.hour == 12:
                forecast = copy.deepcopy(forcast_day)

            total_precipitation = total_precipitation + forcast_day._total_precipitation

        if forecast is None:
            # We passed 12 noon, set to current
            forecast = forecasts_day[0]

        forecast._temperature_max = forecast_temp_max
        forecast._temperature_min = forecast_temp_min
        forecast._total_precipitation = total_precipitation
        forecast._mean_precipitation = total_precipitation / 24
        forecasts.append(forecast)
        day_nr = day_nr + 1

    return forecasts


# pylint: disable=R0914, R0912, W0212, R0915


def _get_all_forecast_from_api(api_result: dict) -> OrderedDict:
    """Converts results fråm API to SmhiForeCast list"""
    # Total time in hours since last forecast
    total_hours_last_forecast = 1.0

    # Last forecast time
    last_time = None

    # Need the ordered dict to get
    # the days in order in next stage
    forecasts_ordered = OrderedDict()

    # Get the parameters
    for forecast in api_result["timeSeries"]:

        valid_time = datetime.strptime(forecast["validTime"], "%Y-%m-%dT%H:%M:%SZ")
        for param in forecast["parameters"]:
            if param["name"] == "t":
                temperature = float(param["values"][0])  # Celcisus
            elif param["name"] == "r":
                humidity = int(param["values"][0])  # Percent
            elif param["name"] == "msl":
                pressure = int(param["values"][0])  # hPa
            elif param["name"] == "tstm":
                thunder = int(param["values"][0])  # Percent
            elif param["name"] == "tcc_mean":
                octa = int(param["values"][0])  # Cloudiness in octas
                if 0 <= octa <= 8:  # Between 0 -> 8
                    cloudiness = round(100 * octa / 8)  # Convert octas to percent
                else:
                    cloudiness = 100  # If not determined use 100%
            elif param["name"] == "Wsymb2":
                symbol = int(param["values"][0])  # category
            elif param["name"] == "pcat":
                precipitation = int(param["values"][0])  # percipitation
            elif param["name"] == "pmean":
                mean_precipitation = float(param["values"][0])  # mean_percipitation
            elif param["name"] == "ws":
                wind_speed = float(param["values"][0])  # wind speed
            elif param["name"] == "wd":
                wind_direction = int(param["values"][0])  # wind direction
            elif param["name"] == "vis":
                horizontal_visibility = float(param["values"][0])  # Visibility
            elif param["name"] == "gust":
                wind_gust = float(param["values"][0])  # wind gust speed

        roundedTemp = int(round(temperature))

        if last_time is not None:
            total_hours_last_forecast = (valid_time - last_time).seconds / 60 / 60

        # Total precipitation, have to calculate with the nr of
        # hours since last forecast to get correct total value
        tp = round(mean_precipitation * total_hours_last_forecast, 2)

        forecast = SmhiForecast(
            roundedTemp,
            roundedTemp,
            roundedTemp,
            humidity,
            pressure,
            thunder,
            cloudiness,
            precipitation,
            wind_direction,
            wind_speed,
            horizontal_visibility,
            wind_gust,
            round(mean_precipitation, 1),
            tp,
            symbol,
            valid_time,
        )

        if valid_time.day not in forecasts_ordered:
            # add a new list
            forecasts_ordered[valid_time.day] = []

        forecasts_ordered[valid_time.day].append(forecast)

        last_time = valid_time

    return forecasts_ordered