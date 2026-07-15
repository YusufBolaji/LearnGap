# LearnGap Phase 5 — Showcase-Ready MVP

LearnGap is a data-driven learning gap detection, intervention, and impact measurement platform.

## New in Phase 5
- Login and role display
- Polished branded interface
- Class, topic, and date filters
- Bulk Excel upload
- Downloadable Excel upload template
- Improved dashboard
- Intervention tracking
- Reassessment and before-vs-after impact
- CSV export
- Deployment configuration

## Demo login
- Administrator: `admin` / `admin123`
- Teacher: `teacher` / `teacher123`

Change these credentials before using the app in a real school.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Excel upload format

### Students sheet
Required columns:
- Student_ID
- Student_Name
- Class

Optional:
- Gender

### Assessments sheet
Required columns:
- Student_ID
- Subject
- Topic
- Score
- Max_Score
- Assessment_Date

## Deploy to Streamlit Community Cloud
1. Push this folder to a GitHub repository.
2. Sign in to Streamlit Community Cloud.
3. Create a new app.
4. Select the repository and set the main file path to `app.py`.
5. Deploy.

## Important production note
SQLite is fine for a demo and single-instance showcase app. For multi-user production use, migrate the database to PostgreSQL or another managed database.
