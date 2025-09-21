from flask import Flask, render_template, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("test.html")  # matches your HTML filename

@app.route("/api/hello")
def hello():
    return jsonify({"message": "Hello from Flask!"})

if __name__ == "__main__":
    app.run(debug=True)

