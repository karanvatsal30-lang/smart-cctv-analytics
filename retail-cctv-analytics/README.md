# Smart CCTV — Universal Store Analytics

A conservative, explainable, and software-only CCTV analytics platform designed for retail stores.

The platform works with any standard CCTV camera without requiring specialized sensors, hardware, or predefined floor plans.

---

## The 4 Approved Analytics Features

1. **Feature 1: Camera-Wide People Counting**
   - Operates across 100% of the camera frame independently.
   - Scale-adaptive tracking with confidence thresholds and honest estimation ranges under occlusion.
   - Never artificially restricted or cropped by user regions.

2. **Feature 2: User-Defined Checkout Congestion Monitoring**
   - Monitors only the user-drawn Checkout Region.
   - Evaluates persistent dwell times ($\ge 6\text{s}$) before flagging potential congestion.
   - Neutral terminology: *"Visible people in checkout: X"*.

3. **Feature 3: User-Defined Shelf Visual-Change Monitor**
   - Monitors only the user-drawn Shelf Region.
   - **Critical Obstruction Gate**: If a person walks in front of the shelf, the system reports *"Shelf view temporarily obstructed by person"* and **never** triggers a false shelf change alert.
   - When the person leaves, enters a 5-frame stabilization window before resuming comparison against the reference baseline.
   - Ambient lighting shift detection separates full-room brightness changes from local shelf stock depletion.

4. **Feature 4: Video & Analytics Reliability Monitoring**
   - Monitors Laplacian blur score, scene contrast, illumination, and occlusion index.
   - If the camera is dark, blurred, or occluded, withholds confident claims and outputs honest uncertainty.

---

## User Identification & Security Architecture

- **No Self-Registration / Account Creation**: Unsolicited account creation forms are removed. Users identify themselves with authorized account credentials or as a station operator.
- **Frontend Security**: Only the publishable Supabase Anon Key is served to client browsers via `/api/config/public`.
- **Backend Security**: `SUPABASE_SERVICE_KEY` and `SUPABASE_JWT_SECRET` are kept strictly server-side.
- **Offline / Local Fallback**: If Supabase is not configured, the app runs in local operator mode without breaking any features or throwing server errors.

---

## Quick Start

### 1. Installation

```bash
pip install -r requirements.txt
```

### 2. Configure Environment (Optional for Cloud Persistence)

Copy `.env.example` to `.env`:

```bash
copy .env.example .env
```

Set your Supabase credentials:
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-publishable-anon-key
SUPABASE_SERVICE_KEY=your-backend-service-role-key
SUPABASE_JWT_SECRET=your-supabase-jwt-secret
```

### 3. Launch Dashboard

Double-click `start_dashboard.bat` or run:

```bash
python run.py
```

Open your browser to [http://127.0.0.1:5000](http://127.0.0.1:5000).

---

## Database Setup (Supabase)

If using Supabase for cloud persistence and Row-Level Security:
1. Go to your Supabase Project Dashboard -> **SQL Editor**.
2. Run the queries in `supabase_setup.sql`.
3. All tables (`profiles`, `cameras`, `monitoring_regions`) and RLS policies will be automatically created.
