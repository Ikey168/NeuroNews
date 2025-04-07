from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/news_sentiment")
def get_news_sentiment(topic: str):
    return {"topic": topic, "sentiment": "Positive"}