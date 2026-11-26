import time

VALID_CITIES = {"北京", "上海", "广州", "深圳", "杭州"}


def weather_query(city, date):
    if city not in VALID_CITIES:
        raise ValueError(f"invalid city: {city}")
    if city == "广州":
        raise TimeoutError("weather service timeout")
    return {"city": city, "date": date, "weather": "晴", "temp": 26}


def news_search(query):
    return {"query": query, "results": [f"{query}相关新闻1", f"{query}相关新闻2"]}


def calculator(a, b, op):
    if op == "+":
        return {"result": a + b}
    if op == "-":
        return {"result": a - b}
    if op == "*":
        return {"result": a * b}
    if op == "/":
        if b == 0:
            raise ValueError("division by zero")
        return {"result": a / b}
    raise ValueError(f"unsupported op: {op}")

def delete_schedule(event_id):
    if event_id == "vip_event":
        raise Exception("429 Too Many Requests")
    return {"status": "deleted", "event_id": event_id}