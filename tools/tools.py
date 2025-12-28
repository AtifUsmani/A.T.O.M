from langchain.tools import tool
from tools.ha_test import HomeAssistant
from tools.wikipedia_search import WikipediaSearcher
from tools.timer import TimerManager
from tools.camera import Camera
from robots.spider_bot import SPIDER
from robots.robotic_arm import RoboticArm
from langchain_community.utilities import SearxSearchWrapper
from memory.memory_tool import retrieve_memory, write_memory_tool_async
import yaml
from debug import tool_calls as tool_log
# from tests.harness import tool_log

with open('config.yaml', "r") as file:
    config = yaml.safe_load(file) or {}

ha_wrapper = HomeAssistant()
search = SearxSearchWrapper(searx_host=config['SEARXNG_URL'])
tm = TimerManager()
quadruped = SPIDER()

if config["ROBOTIC_ARM"]:
    try:
        robotarm = RoboticArm()
    except Exception as e:
        print(f"[WARN] Failed to connect to Robotic Arm: {e}")
        print("🤖 Robotic Arm disabled")
        robotarm = None
else:
    robotarm = None
    print("🤖 Robotic Arm disabled")

def close_connections():
    """Ends connections to robots and other resources."""
    try:
        quadruped.close_connection()
    except Exception:
        pass

    try:
        robotarm.robot_control.close_connection()
    except Exception:
        pass

@tool
def move_robotic_arm(x: float, y: float, z: float, speed: int = 50) -> str:
    """
    Move the robotic arm to specified (x, y, z) coordinates at given speed.

    Parameters
    ----------
    x : float
        X coordinate in cm. (0 to 20)
    y : float
        Y coordinate in cm. (0 to 20)
    z : float
        Z coordinate in cm. (0 to 24)
    speed : int, optional
        Speed of movement (default is 50).

    Returns
    -------
    str
        Confirmation message with target coordinates.
    """
    if config["ROBOTIC_ARM"]:
        try:
            response = robotarm.move_to(x, y, z, speed)
            tool_log.record_tool_call("move_robotic_arm", {"response": response})
            return response
        except:
            response = 'Movement failed to execute'
            tool_log.record_tool_call("move_robotic_arm", {"response": response})
            return response
        
    else:
        return "Robotic arm disabled in config.yaml file."

@tool
def draw_circle_robot_arm(radius: int, cycles: int, center: tuple) -> str:
    """
    Instruct the robotic arm to draw a circle of given radius on specified plane.
    Parameters
    ----------
    radius : int
        Radius of the circle in cm.
    cycles : int
        Number of complete circles to draw.
    center : tuple
        Center point (x, y, z) of the circle in cm.    
        Safe value (16,6,4)
    Returns
    -------
    str
        Confirmation message after drawing the circle.
    """
    if config["ROBOTIC_ARM"]:
        try:
            robotarm.draw_circle(
                center=center, radius=radius, plane="XY", cycles=cycles
            )
            response = "Robotic arm has drawn a circle."
            tool_log.record_tool_call("draw_circle_robot_arm", {"response": response})
            return response
        except:
            response = 'Movement failed to execute'
            tool_log.record_tool_call("draw_circle_robot_arm", {"response": response})
            return response
    else:
        return "Robotic arm disabled in config.yaml file."

@tool
def draw_rectangle_robot_arm(center: tuple, width: float, height: float) -> str:
    """
    Instruct the robotic arm to draw a rectangle of given width and height on specified plane.
    Parameters
    ----------
    center : tuple
        Center point (x, y, z) of the rectangle in cm.
        Safely value (6,4,12)
    width : float
        Width of the rectangle in cm.
    height : float
        Height of the rectangle in cm.

    Returns
    -------
    str
        Confirmation message after drawing the rectangle.
    """
    if config["ROBOTIC_ARM"]:
        try:
            robotarm.draw_rectangle(
            center=center,
            width=width,
            height=height,
            plane="XZ"
            )
            response = "Robotic arm has drawn a rectangle."
            tool_log.record_tool_call("draw_rectangle_robot_arm", {"response": response})
            return response
        except:
            response = 'Movement failed to execute'
            tool_log.record_tool_call("draw_rectangle_robot_arm", {"response": response})
            return response
        
    else:
        return "Robotic arm disabled in config.yaml file."

@tool
def search_web(query: str):
    """
    Perform a web search and return a brief summary of results based on a searched query using SearXNG search engine.
    """
    response = search.run(query)
    tool_log.record_tool_call("search_web", {"response": response})
    return response

@tool
def greet_user() -> str:
    """Greet the user through the Spider bot Quadruped robot."""
    response = quadruped.greet()
    tool_log.record_tool_call("greet_user", {"response": response})
    return response

@tool
def dance_quadruped(dance_number: int) -> str:
    """Make the quadruped dance. Can be used to express happiness. Dance_number should be 1,2 or 3."""
    response = quadruped.dance(dance_number=dance_number)
    tool_log.record_tool_call("dance_quadruped", {"response": response})
    return response

@tool
def get_temperature() -> str:
    """Retrieves the current room temperature from Home Assistant."""
    try:
        response = ha_wrapper.get_temperature()
        tool_log.record_tool_call("get_temperature", {
            "success": True,
            "response": response
        })
        return response
    except Exception as e:
        tool_log.record_tool_call("get_temperature", {
            "success": False,
            "error": str(e)
        })
        return f"[ERROR] Failed to get temperature: {e}"

@tool
def get_humidity() -> str:
    """Retrieves the current room humidity from Home Assistant."""
    try:
        response = ha_wrapper.get_humidity()
        tool_log.record_tool_call("get_humidity", {"response": response})
        return response
    except Exception as e:
        return f"[ERROR] Failed to get humidity: {e}"

@tool
def toggle_wled(query: str) -> str:
    """Turns WLED on/off

    Parameters
    ----------
    desired_state : str
        The state you want the light to be in. Accepts:
        - "on"
        - "off"
    
    """
    try:
        response = ha_wrapper.ensure_wled_state(desired_state=query)
        tool_log.record_tool_call("toggle_wled", {"response": response})
        # print("TOOL     TOOL_LOG =", id(tool_log.TOOL_CALL_LOG))
        # print("Memory tool recorded")
        return response
    except Exception as e:
        return f"[ERROR] Failed to toggle WLED: {e}"

@tool
def get_light_state() -> str:
    """Checks the current state of the WLED light (on/off)."""
    try:
        response = ha_wrapper.get_light_state()
        tool_log.record_tool_call("get_light_state", {"response": response})
        return response
    except Exception as e:
        return f"[ERROR] Failed to get light state: {e}"

@tool
def set_timer(duration: int, task_name: str) -> str:
    """
    Sets a timer with the specified duration and task name.
    """
    try:
        tm.set_timer(duration, task_name, tm.alert)
        timers = tm.list_timers()
        response = {"Active timers": timers}
        tool_log.record_tool_call("set_timer", {"response": response})
        return response
    except Exception as e:
        return f"[ERROR] Failed to set timer '{task_name}': {e}"

@tool
def cancel_timer(task_name: str) -> str:
    """
    Cancels a previously scheduled timer.
    """
    try:
        tm.cancel_timer(task_name)
        response = f"Timer '{task_name}' canceled successfully."
        tool_log.record_tool_call("cancel_timer", {"response": response})
        return response
    except Exception as e:
        return f"[ERROR] Failed to cancel timer '{task_name}': {e}"

@tool
def list_timers() -> str:
    """
    Retrieves a list of currently active timers.
    """
    try:
        timers = tm.list_timers()
        response = str({"Active timers": timers})
        tool_log.record_tool_call("list_timers", {"response": response})
        return response
    except Exception as e:
        return f"[ERROR] Failed to list timers: {e}"

@tool(return_direct=False)
def capture_and_analyze_photo(query: str) -> str:
    """
    Captures an image using the assistant's onboard camera and sends it to the
    vision-enabled LLM for interpretation. This function is used to give the
    assistant ("ATOM") real-time visual awareness.

    Workflow:
        1. Initializes the camera.
        2. Captures a single photo frame.
        3. Submits the image and the user-provided query to the LLM for analysis.
        4. Returns the analysis result as a JSON-formatted string.

    Args:
        query (str): A natural-language prompt that describes what the assistant
                     should look for or analyze in the captured image.

    Returns:
        str: A JSON-serializable string containing the LLM's analysis, or an
             error message beginning with "[ERROR]" if any step fails.

    Notes:
        - Camera initialization, image capture, and LLM analysis are all wrapped
          in explicit error handling so ATOM can respond gracefully to hardware
          or runtime issues.
        - The returned string is safe for direct speech output or logging by
          the assistant.
    """
    try:
        webcam = Camera()
    except Exception as e:
        return f"[ERROR] Failed to initialize camera: {e}"

    try:
        analysis = webcam.llm(prompt=query)
    except Exception as e:
        return f"[ERROR] Failed to analyze captured photo: {e}"

    try:
        return str({"analysis": analysis})
    except Exception as e:
        return f"[ERROR] Failed to serialize analysis: {e}"

@tool
def get_date_time() -> str:
    """Returns the current date and time."""
    try:
        import datetime
        now = datetime.datetime.now()
        result = {
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
        }
        tool_log.record_tool_call("get_date_time", {"response": result})
        return str(result)
    except Exception as e:
        return f"[ERROR] Failed to get date/time: {e}"

def extract_from_json(_) -> str:
    """Retrieves data from a json file."""
    import json

    with open("data.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    tool_log.record_tool_call("extract_from_json", {"response": data})
    return data

@tool
def create_file(name: str, content: str) -> str:
    """Create a file with the given name and content. Can be used for making python scripts and CSV files."""
    from pathlib import Path

    dest_path = Path(f'generated/{name}')
    if dest_path.exists():
        return "Error: File already exists."
    try:
        dest_path.write_text(content, encoding="utf-8")
    except Exception as exc:
        return "Error: {exc!r}"
    tool_log.record_tool_call("create_file", {"response": "File created."})
    return "File created."

@tool
def web_search(query: str) -> str:
    """
    Use this if search_web fails.
    Perform a web search and return a brief summary of results based on a searched query using DuckDuckGo search engine.
    """
    from langchain_community.tools import DuckDuckGoSearchRun

    try:
       search = DuckDuckGoSearchRun()
       response = {'search_result': search.invoke(query)}
       tool_log.record_tool_call("web_search", {"response": response})
       return response

    except Exception as e:
        response = f"An unexpected error occurred during web search: {str(e)}"
        tool_log.record_tool_call("web_search", {"response": response})
        return response

@tool
def create_pdf(filename: str, title: str, content: str, table_data=None) -> str:
    """
    Safely create a professional PDF with title, paragraphs, and optional tables.
    Includes full error handling for file, ReportLab, and data issues.
    Saves the file inside the 'generated' folder.
    """
    import os

    # Ensure output directory exists
    output_dir = "generated"
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        return f"[ERROR] Could not create output directory: {e}"

    # Build full file path
    filename = os.path.join(output_dir, filename)

    # Validate basic params
    if not isinstance(filename, str) or not filename.strip():
        return "[ERROR] Invalid filename."

    if not isinstance(title, str):
        return "[ERROR] Title must be a string."

    if not isinstance(content, str):
        return "[ERROR] Content must be a string."

    # Import ReportLab
    try:
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
    except Exception as e:
        return f"[ERROR] Failed to import ReportLab modules: {e}"

    try:
        styles = getSampleStyleSheet()
        story = []

        doc = SimpleDocTemplate(
            filename,
            pagesize=A4,
            leftMargin=40, rightMargin=40,
            topMargin=40, bottomMargin=40
        )

        # Title
        story.append(Paragraph(f"<b><font size=16>{title}</font></b>", styles["Title"]))
        story.append(Spacer(1, 20))

        # Body paragraphs
        for line in content.split("\n"):
            story.append(Paragraph(line, styles["BodyText"]))
            story.append(Spacer(1, 12))

        # Optional table
        if table_data:
            if not isinstance(table_data, (list, tuple)):
                return "[ERROR] table_data must be a list/tuple of rows."

            # Validate rows have equal length
            row_lengths = {len(row) for row in table_data}
            if len(row_lengths) > 1:
                return "[ERROR] All table rows must have the same number of columns."

            table = Table(table_data, hAlign="LEFT")
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ]))

            story.append(Spacer(1, 20))
            story.append(table)

        # Build PDF
        doc.build(story)
        response = f"PDF successfully created at {filename}"
        tool_log.record_tool_call("create_pdf", {"response": response})
        return response

    except Exception as e:
        response = f"[ERROR] Unexpected failure: {e}"
        tool_log.record_tool_call("create_pdf", {"response": response})
        return response

@tool
def search_wikipedia(query: str, full_page_content: bool):
    """
    Search Wikipedia for the given query.

    Parameters
    ----------
    query : str
        The search term to look up on Wikipedia.
    full_page_content : bool
        If True, return the full page content.
        If False, return only a summary of the page.

    Returns
    -------
    dict
        A dictionary containing either:
        - {"Full Page Content": <full text>} if full_page_content is True
        - {"Summary": <summary text>} if full_page_content is False

    Notes
    -----
    This function uses the `WikipediaSearcher` class with a custom user agent
    (`my-custom-ai-agent/1.0`) to perform the lookup.
    """

    searcher = WikipediaSearcher(user_agent="my-custom-ai-agent/1.0")

    if full_page_content:
        response = {"Full Page Content": searcher.search_full_page(query)}
        tool_log.record_tool_call("search_wikipedia", {"response": response})
        return response
    else:
        response = {"Summary": searcher.search_summary(query)}
        tool_log.record_tool_call("search_wikipedia", {"response": response})
        return response

@tool
def get_weather(city: str) -> dict:
    """
    Fetch current weather information for a given city using the free Open-Meteo API.

    This function performs the following steps:
    1. Converts the city name into geographic coordinates (latitude & longitude)
       using Open-Meteo's geocoding service (no API key required).
    2. Fetches the current weather for those coordinates from the Open-Meteo
       weather API.
    3. Returns the result as a Python dictionary, suitable for ingestion by
       LangChain agents or other LLM apps.

    Parameters
    ----------
    city : str
        Name of the city to retrieve weather information for.

    Returns
    -------
    dict
        A dictionary containing weather details such as temperature, wind speed,
        conditions, etc. Returns an error dict if the city is not found or if the
        API request fails.

    Example
    -------
    >>> get_weather("London")
    {
        'city': 'London',
        'latitude': 51.5085,
        'longitude': -0.1257,
        'temperature_celsius': 12.3,
        'wind_speed': 5.1,
        'weather_code': 3,
        'raw': {...}
    }

    Notes
    -----
    - This function uses the Open-Meteo API: https://open-meteo.com
    - No API key is required.
    - The weather data might be a bit old. Check the time for when it was last updated.
    """

    import requests

    WEATHER_CODES = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        80: "Rain showers",
        95: "Thunderstorm",
        99: "Thunderstorm with hail",
    }

    # -----------------------------
    # Validate input
    # -----------------------------
    if not isinstance(city, str) or not city.strip():
        return {"error": "Invalid city name. Must be a non-empty string."}

    city = city.strip()

    # -----------------------------
    # Step 1: Geocoding
    # -----------------------------
    geocode_url = "https://geocoding-api.open-meteo.com/v1/search"
    g_params = {"name": city, "count": 1, "language": "en", "format": "json"}

    try:
        geo_res = requests.get(geocode_url, params=g_params, timeout=10)
        geo_res.raise_for_status()
        geo_data = geo_res.json()
    except requests.Timeout:
        return {"error": "Geocoding request timed out."}
    except requests.ConnectionError:
        return {"error": "Failed to connect to geocoding service."}
    except ValueError:
        return {"error": "Failed to parse geocoding response (invalid JSON)."}
    except Exception as e:
        return {"error": f"Unexpected geocoding error: {e}"}

    if not geo_data.get("results"):
        return {"error": f"City '{city}' not found."}

    try:
        location = geo_data["results"][0]
        lat = float(location["latitude"])
        lon = float(location["longitude"])
    except Exception:
        return {"error": "Invalid geocoding data received from API."}

    # -----------------------------
    # Step 2: Weather Fetch
    # -----------------------------
    weather_url = "https://api.open-meteo.com/v1/forecast"
    w_params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": True,
    }

    try:
        weather_res = requests.get(weather_url, params=w_params, timeout=10)
        weather_res.raise_for_status()
        weather_data = weather_res.json()
    except requests.Timeout:
        return {"error": "Weather request timed out."}
    except requests.ConnectionError:
        return {"error": "Failed to connect to weather service."}
    except ValueError:
        return {"error": "Failed to parse weather response (invalid JSON)."}
    except Exception as e:
        return {"error": f"Unexpected weather API error: {e}"}

    current = weather_data.get("current_weather")
    if not current:
        return {"error": "Weather data unavailable for this location."}

    # -----------------------------
    # Step 3: Format Output
    # -----------------------------
    try:
        code = current.get("weathercode")
        desc = WEATHER_CODES.get(code, "Unknown weather")

        response = {
            "city": location.get("name", city),
            "latitude": lat,
            "longitude": lon,
            "temperature_celsius": current.get("temperature"),
            "wind_speed": current.get("windspeed"),
            "weather_code": code,
            "description": desc,
            "raw": weather_data,
        }
        tool_log.record_tool_call("get_weather", {"response": response})
        return response
    except Exception as e:
        response = {"error": f"Failed to format weather data: {e}"}
        tool_log.record_tool_call("get_weather", {"response": response})
        return response

@tool
def geocode_city(city: str) -> dict:
    """
    Convert a city name into latitude/longitude using the free Open-Meteo geocoding API.

    Parameters
    ----------
    city : str
        Name of the city to look up.

    Returns
    -------
    dict
        Dictionary containing city name, country, latitude, longitude, and raw data.
        Returns an error dict if lookup fails.

    Notes
    -----
    - API is completely free and requires no key.
    - Source: https://open-meteo.com/
    """

    import requests

    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": city, "count": 1, "format": "json"}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "results" not in data or not data["results"]:
            return {"error": f"City '{city}' not found."}

        loc = data["results"][0]

        response = {
            "city": loc["name"],
            "country": loc.get("country"),
            "latitude": loc["latitude"],
            "longitude": loc["longitude"],
            "raw": data
        }

        tool_log.record_tool_call("geocode_city", {"response": response})
        return response

    except Exception as e:
        response = {"error": f"Failed to fetch geolocation: {str(e)}"}
        tool_log.record_tool_call("geocode_city", {"response": response})
        return response

@tool
def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    """
    Convert currency using exchangerate.host with retries and fallback.

    Returns
    -------
    dict
        {
            "success": True/False,
            "amount": float,
            "from": "USD",
            "to": "INR",
            "converted_amount": float,
            "rate_used": float,
            "date": "YYYY-MM-DD",
            "error": Optional[str]
        }
    """

    import requests
    import time

    def safe_log(payload):
        try:
            tool_log.record_tool_call("convert_currency", payload)
        except Exception:
            pass

    # Normalize
    try:
        amount = float(amount)
    except Exception:
        resp = {"success": False, "error": "Amount must be numeric"}
        safe_log(resp)
        return resp

    from_currency = str(from_currency).upper()
    to_currency = str(to_currency).upper()

    if len(from_currency) != 3 or len(to_currency) != 3:
        resp = {"success": False, "error": "Currency codes must be 3-letter ISO format"}
        safe_log(resp)
        return resp

    # Primary endpoint
    convert_url = (
        f"https://api.exchangerate.host/convert"
        f"?from={from_currency}&to={to_currency}&amount={amount}"
    )

    # Retry logic
    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            r = requests.get(convert_url, timeout=8)
            r.raise_for_status()
            data = r.json()

            if not data.get("success", False):
                raise Exception("API returned failure")

            result = {
                "success": True,
                "amount": amount,
                "from": from_currency,
                "to": to_currency,
                "converted_amount": round(data["result"], 4),
                "rate_used": data["info"]["rate"],
                "date": data.get("date"),
            }
            safe_log(result)
            return result

        except Exception as e:
            if attempt == attempts:
                break
            time.sleep(0.7 * attempt)

    # ---------- FALLBACK ----------
    # If /convert fails, fallback to /latest
    try:
        latest = requests.get(
            "https://api.exchangerate.host/latest", timeout=8
        )
        latest.raise_for_status()
        data = latest.json()

        rates = data.get("rates", {})
        if not rates or from_currency not in rates or to_currency not in rates:
            raise Exception("Rates unavailable")

        eur_value = amount / rates[from_currency]
        converted = eur_value * rates[to_currency]

        result = {
            "success": True,
            "amount": amount,
            "from": from_currency,
            "to": to_currency,
            "converted_amount": round(converted, 4),
            "rate_used": rates[to_currency] / rates[from_currency],
            "date": data.get("date"),
        }
        safe_log(result)
        return result

    except Exception as e:
        resp = {
            "success": False,
            "error": f"Currency conversion failed after retries: {str(e)}",
        }
        safe_log(resp)
        return resp

@tool
def ip_geolocation(ip_address: str = "") -> dict:
    """
    Get geolocation information for an IP address using the free ipapi.co API.

    Parameters
    ----------
    ip_address : str, optional
        IP address to lookup. If empty, the API returns data for the caller IP.

    Returns
    -------
    dict
        Geolocation data including city, region, country, latitude, longitude.
        Returns an error dict if lookup fails.

    Notes
    -----
    - API: https://ipapi.co/ (no API key required)
    """
    
    import requests

    _ip_cache = {}

    if ip_address in _ip_cache:
        return _ip_cache[ip_address]

    primary = f"https://ipapi.co/{ip_address}/json/"
    fallback = f"http://ipwho.is/{ip_address}"

    try:
        r = requests.get(primary, timeout=8)
        if r.status_code == 429:
            raise Exception("rate_limited")
        r.raise_for_status()
        data = r.json()
    except Exception:
        try:
            r = requests.get(fallback, timeout=8)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            return {"error": f"IP lookup failed: {str(e)}"}

    _ip_cache[ip_address] = data
    tool_log.record_tool_call("ip_geolocation", {"response": data})
    return data

@tool
def fetch_and_parse(url: str) -> dict:
    """
    Fetch a webpage and extract its title + main text using BeautifulSoup.

    Parameters
    ----------
    url : str
        URL of the webpage to scrape.

    Returns
    -------
    dict
        Contains the page title, extracted text, and raw HTML.
        Returns an error dict if fetching or parsing fails.

    Notes
    -----
    - Only works on publicly accessible pages (no login required).
    - Uses requests + BeautifulSoup (no API key).
    """

    import requests
    from bs4 import BeautifulSoup

    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()

        soup = BeautifulSoup(res.text, "html.parser")

        title = soup.title.string.strip() if soup.title else "No title"

        # Extract visible text
        for script in soup(["script", "style"]):
            script.extract()
        text = " ".join(soup.get_text(separator=" ").split())

        response = {
            "url": url,
            "title": title,
            "text": text,
            "raw_html": res.text
        }

        tool_log.record_tool_call("fetch_and_parse", {"response": response})
        return response

    except Exception as e:
        response = {"error": f"Web scraping failed: {str(e)}"}
        tool_log.record_tool_call("fetch_and_parse", {"response": response})
        return response
    
@tool
def calculate(expression: str) -> dict:
    """
    Safely evaluate a mathematical expression using Python's math module.

    Parameters
    ----------
    expression : str
        A math expression (e.g., '2+2', 'sqrt(16) + sin(1.5)').

    Returns
    -------
    dict
        Result of the calculation or an error message.

    Notes
    -----
    - Uses a safe namespace (no access to builtins or system functions).
    - Provides access to functions in Python's `math` module.
    """

    import math

    safe_namespace = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}

    try:
        result = eval(expression, {"__builtins__": {}}, safe_namespace)
        tool_log.record_tool_call("calculate", {"response": result})
        return {"expression": expression, "result": result}

    except Exception as e:
        response = {"error": f"Calculation failed: {str(e)}"}
        tool_log.record_tool_call("calculate", {"response": response})
        return response

@tool
def retrieve_memories(query: str) -> str:
    """
    Retrieve relevant long-term memory from Chroma.
    Returns a short compressed memory block or empty string.
    """
    response = retrieve_memory(query=query)
    tool_log.record_tool_call("retrieve_memories", {"response": response})
    return response

@tool
def save_memory(memory_text: str) -> str:
    """
    Asynchronously process and store long-term memory using a judge LLM.

    Flow (non-blocking):
    - Always treat incoming memory as valid
    - Search for similar existing memories
    - Ask judge LLM to decide:
        - add_new          -> store as separate memory
        - update_existing  -> replace an existing memory
        - skip             -> do nothing
    - Apply DB changes in the background
    - Tool returns immediately
    """
    response = write_memory_tool_async.invoke({
        "memory_text": memory_text
    })
    tool_log.record_tool_call("save_memory", {"memory_text": response})
    return response

tools = [get_temperature,
         get_date_time,
         get_humidity,
         toggle_wled,
         get_light_state,
         create_file,
         web_search,
         search_web,
         create_pdf,
         search_wikipedia,
         set_timer,
         list_timers,
         cancel_timer,
         get_weather,
         geocode_city,
         convert_currency,
         ip_geolocation,
         fetch_and_parse,
         calculate,
         capture_and_analyze_photo,
         greet_user,
         dance_quadruped,
         retrieve_memories,
         save_memory,
         move_robotic_arm,
         draw_circle_robot_arm,
         draw_rectangle_robot_arm
        ]