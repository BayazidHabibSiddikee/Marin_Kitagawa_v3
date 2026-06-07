import os
import sys
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

app = FastAPI()

# Point to parent dir to serve the whole app if needed
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@app.get("/", response_class=HTMLResponse)
async def get_index():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Marin Brain Topology</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        body { background: #0a0a0c; color: #4db8a4; font-family: 'Cinzel'; margin: 0; overflow: hidden; }
        .node circle { stroke: #4db8a4; stroke-width: 2px; }
        .node text { fill: #e8ddd0; font-size: 10px; font-family: 'Rajdhani'; }
        .link { stroke: rgba(77, 184, 164, 0.2); stroke-width: 1px; }
        h1 { position: absolute; top: 20px; left: 20px; font-size: 1.5rem; letter-spacing: 2px; }
    </style>
</head>
<body>
    <h1>MODULEFLOW: COGNITIVE MAP</h1>
    <svg width="100vw" height="100vh"></svg>
    <script>
        fetch('/moduleflow/graph.json').then(r => r.json()).then(data => {
            const svg = d3.select("svg"),
                  width = window.innerWidth,
                  height = window.innerHeight;

            const simulation = d3.forceSimulation(data.nodes)
                .force("link", d3.forceLink(data.links).id(d => d.id).distance(150))
                .force("charge", d3.forceManyBody().strength(-300))
                .force("center", d3.forceCenter(width / 2, height / 2));

            const link = svg.append("g").selectAll("line")
                .data(data.links).enter().append("line").attr("class", "link");

            const node = svg.append("g").selectAll(".node")
                .data(data.nodes).enter().append("g").attr("class", "node")
                .call(d3.drag().on("start", dragstarted).on("drag", dragged).on("end", dragended));

            node.append("circle").attr("r", 10).attr("fill", d => d.type === 'brain' ? '#4db8a4' : '#c9965a');
            node.append("text").attr("dx", 15).attr("dy", 4).text(d => d.label);

            simulation.on("tick", () => {
                link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
                    .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
                node.attr("transform", d => `translate(${d.x},${d.y})`);
            });

            function dragstarted(event) { if (!event.active) simulation.alphaTarget(0.3).restart(); event.subject.fx = event.subject.x; event.subject.fy = event.subject.y; }
            function dragged(event) { event.subject.fx = event.x; event.subject.fy = event.y; }
            function dragended(event) { if (!event.active) simulation.alphaTarget(0); event.subject.fx = null; event.subject.fy = null; }
        });
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5070)
