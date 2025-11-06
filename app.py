from flask import Flask, request, jsonify
app = Flask(__name__)

@app.post("/automation")
def automation():
    data = request.get_json(force=True)
    name = data.get("name")
    job_title = data.get("job_title")
    return jsonify({"ok": True, "message": f"Hello {name} ({job_title})"})

if __name__ == "__main__":
    # 0.0.0.0 listens on all interfaces; localhost only is fine too
    app.run(host="0.0.0.0", port=3000)
