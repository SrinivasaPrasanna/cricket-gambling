from fastapi import FastAPI, Response, HTTPException
import orjson, os, time

OUTFILE = "data/live_cricket.json"

app = FastAPI(title="Radhe Live Cricket API", docs_url=None, redoc_url=None)

@app.get("/live.json")
def live_json():
    if not os.path.exists(OUTFILE):
        raise HTTPException(503, "No data yet")
    with open(OUTFILE, "rb") as f:
        data = f.read()
    return Response(content=data, media_type="application/json")

@app.get("/")
def health():
    return {"ok": True, "ts": int(time.time())}
