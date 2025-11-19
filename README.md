# EistBuild_app
```markdown
# EstiBuild — Streamlit prototype

EstiBuild is an educational Streamlit application for quick building area and material estimation
from AutoCAD DXF line-plans. It is designed as a final year B.Tech Civil project prototype.

Features
- Upload DXF (recommended) and convert to polygonized line-plan
- Compute built-up area, carpet area (using inward offset), perimeter
- Approximate long-wall / short-wall method via bounding box
- Estimate material quantities for a simplified set of 12 work items (excavation → painting)
- Export measurement sheet and abstract to Excel

Limitations & Notes
- Prefer DXF. DWG is proprietary — export to DXF from AutoCAD or use an external converter.
- Parsing complex CAD drawings may require cleaning layers or ensuring closed polylines.
- Material estimates use simplified engineering assumptions and should be validated against local standards.
- Units: The app assumes the DXF coordinates match the selected units (meters/feet). Convert drawings if needed.

How to run
1. Create & activate a virtual environment:
   - python -m venv venv
   - source venv/bin/activate (macOS/Linux) or venv\Scripts\activate (Windows)

2. Install dependencies:
   - pip install -r requirements.txt

3. Run Streamlit:
   - streamlit run EstiBuild_app.py

What's next — suggested improvements
- Add DWG -> DXF server-side conversion or explicit instructions for DWG users.
- Improve DXF parsing: ignore utility lines, detect room labels, allow user to select polygons as rooms.
- Add per-room metadata (room name, height, finish) for more accurate BOQ.
- Add cost database (unit rates) and labour estimations.
- Add authentication and project save/load.
