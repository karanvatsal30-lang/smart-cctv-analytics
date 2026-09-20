/**
 * Smart CCTV — Universal Store Analytics Controller.
 * 
 * Features:
 * 1. User Account Creation for First-Time Users & User Identification (Supabase + Local Secure Storage)
 * 2. Per-User CCTV Camera Details & Monitoring Regions Persistence
 * 3. Real-time polling for the 4 core approved analytics features:
 *    - Camera-Wide People Counting (100% frame)
 *    - User-Defined Checkout Congestion (temporal persistence)
 *    - User-Defined Shelf Visual-Change Monitor (obstruction gate)
 *    - Video / Analytics Reliability Monitor
 * 4. Interactive user-region drawing (Checkout & Shelf regions)
 * 5. Video source switching & shelf baseline calibration
 * 6. Evidence Audit trail inspection
 * 7. One-click Dashboard Log Out button
 */

document.addEventListener("DOMContentLoaded", () => {
  const API_BASE = (window.location.protocol === "file:" || !window.location.port) 
    ? "http://127.0.0.1:5000" 
    : "";

  // -----------------------------------------------------------
  // AUTHENTICATION & USER IDENTIFICATION STATE
  // -----------------------------------------------------------
  let supabaseClient = null;
  let currentUserToken = null;
  let currentUserId = null;
  let currentUserDisplayName = "Store Manager";
  let authConfiguredOnServer = false;

  // Auth Gate Elements
  const authGate = document.getElementById("auth-gate");
  const appDashboard = document.getElementById("app-dashboard");
  const tabBtnLogin = document.getElementById("tab-btn-login");
  const tabBtnSignup = document.getElementById("tab-btn-signup");

  const authPanelLogin = document.getElementById("auth-panel-login");
  const authPanelSignup = document.getElementById("auth-panel-signup");
  const authPanelQuick = document.getElementById("auth-panel-quick");
  const authPanelReset = document.getElementById("auth-panel-reset");

  // Sign In Inputs
  const loginEmail = document.getElementById("login-email");
  const loginPassword = document.getElementById("login-password");
  const btnLogin = document.getElementById("btn-login");
  const authErrorLogin = document.getElementById("auth-error-login");
  const linkToSignupFromLogin = document.getElementById("link-to-signup-from-login");

  // Create Account Inputs (First-Time Users)
  const signupName = document.getElementById("signup-name");
  const signupEmail = document.getElementById("signup-email");
  const signupPassword = document.getElementById("signup-password");
  const signupCctvName = document.getElementById("signup-cctv-name");
  const btnSignup = document.getElementById("btn-signup");
  const authErrorSignup = document.getElementById("auth-error-signup");
  const authSuccessSignup = document.getElementById("auth-success-signup");
  const linkToLoginFromSignup = document.getElementById("link-to-login-from-signup");

  // Quick Station Mode
  const quickUserName = document.getElementById("quick-user-name");
  const btnQuickLogin = document.getElementById("btn-quick-login");
  const linkToQuickId = document.getElementById("link-to-quick-id");
  const linkToLoginFromQuick = document.getElementById("link-to-login-from-quick");

  // Password Reset
  const resetEmail = document.getElementById("reset-email");
  const btnReset = document.getElementById("btn-reset");
  const authErrorReset = document.getElementById("auth-error-reset");
  const authSuccessReset = document.getElementById("auth-success-reset");
  const linkToReset = document.getElementById("link-to-reset");
  const linkToLoginFromReset = document.getElementById("link-to-login-from-reset");

  // Dashboard Header User Elements
  const userPill = document.getElementById("user-pill");
  const userDisplayName = document.getElementById("user-display-name");
  const btnLogout = document.getElementById("btn-logout");

  // Video and Header Elements
  const cctvStreamImg = document.getElementById("cctv-stream-img");
  const videoSourcePill = document.getElementById("video-source-pill");
  const videoSourceText = document.getElementById("video-source-text");
  const streamNameText = document.getElementById("stream-name-text");
  const streamFpsBadge = document.getElementById("stream-fps-badge");

  // Error Banner
  const errorBanner = document.getElementById("connection-error-banner");
  const bannerTitle = document.getElementById("banner-title");
  const bannerMsg = document.getElementById("banner-msg");
  const bannerDismiss = document.getElementById("banner-dismiss");

  // Feature 1: Camera-Wide People Count
  const f1PeopleCount = document.getElementById("f1-people-count");
  const f1PeopleDesc = document.getElementById("f1-people-desc");
  const f1ReliabilityBadge = document.getElementById("f1-reliability-badge");
  const f1OcclusionText = document.getElementById("f1-occlusion-text");

  // Feature 2: Checkout Congestion
  const f2RegionName = document.getElementById("f2-region-name");
  const f2StatusText = document.getElementById("f2-status-text");
  const f2PeopleCount = document.getElementById("f2-people-count");
  const f2Explanation = document.getElementById("f2-explanation");
  const f2ReliabilityBadge = document.getElementById("f2-reliability-badge");
  const f2DwellText = document.getElementById("f2-dwell-text");

  // Feature 3: Shelf Monitor
  const f3RegionName = document.getElementById("f3-region-name");
  const f3StatusText = document.getElementById("f3-status-text");
  const f3ChangePct = document.getElementById("f3-change-pct");
  const f3Explanation = document.getElementById("f3-explanation");
  const f3ReliabilityBadge = document.getElementById("f3-reliability-badge");
  const btnToggleShelfSim = document.getElementById("btn-toggle-shelf-sim");
  const btnCalibrateShelf = document.getElementById("btn-calibrate-shelf");

  // Feature 4: System Reliability
  const f4OverallBadge = document.getElementById("f4-overall-badge");
  const relVideoText = document.getElementById("rel-video-text");
  const relPeopleText = document.getElementById("rel-people-text");
  const relCheckoutText = document.getElementById("rel-checkout-text");
  const relShelfText = document.getElementById("rel-shelf-text");
  const dotVideo = document.getElementById("dot-video");
  const dotPeople = document.getElementById("dot-people");
  const dotCheckout = document.getElementById("dot-checkout");
  const dotShelf = document.getElementById("dot-shelf");
  const relClarityScore = document.getElementById("rel-clarity-score");

  // Toolbar Toggles
  const toggleBoxes = document.getElementById("toggle-boxes");
  const toggleRegions = document.getElementById("toggle-regions");
  const togglePrivacy = document.getElementById("toggle-privacy");

  // Modals & Triggers
  const modalRegions = document.getElementById("modal-regions");
  const btnOpenRegions = document.getElementById("btn-open-regions");
  const btnEditCheckoutShortcut = document.getElementById("btn-edit-checkout-shortcut");
  const btnEditShelfShortcut = document.getElementById("btn-edit-shelf-shortcut");

  const modalSource = document.getElementById("modal-source");
  const btnOpenSource = document.getElementById("btn-open-source");

  const modalAudit = document.getElementById("modal-audit");
  const btnOpenAudit = document.getElementById("btn-open-audit");
  const auditLogContent = document.getElementById("audit-log-content");
  const modalCloseBtns = document.querySelectorAll(".modal-close");

  // Region Config Inputs
  const inputCheckoutName = document.getElementById("input-checkout-name");
  const inputShelfName = document.getElementById("input-shelf-name");
  const btnSaveRegionNames = document.getElementById("btn-save-region-names");
  const btnModalCalibrateShelf = document.getElementById("btn-modal-calibrate-shelf");

  // Interactive Drawing Elements
  const drawingCanvas = document.getElementById("region-drawing-canvas");
  const drawingToolbar = document.getElementById("drawing-toolbar");
  const btnDrawCheckout = document.getElementById("btn-draw-checkout");
  const btnDrawShelf = document.getElementById("btn-draw-shelf");
  const btnCancelDrawing = document.getElementById("btn-cancel-drawing");
  const btnStartDrawCheckout = document.getElementById("btn-start-draw-checkout");
  const btnStartDrawShelf = document.getElementById("btn-start-draw-shelf");

  // Video Source Elements
  const btnSrcBenchmark = document.getElementById("btn-src-benchmark");
  const btnUploadFile = document.getElementById("btn-upload-file");
  const videoFileInput = document.getElementById("video-file-input");
  const btnSrcWebcam = document.getElementById("btn-src-webcam");
  const webcamIndex = document.getElementById("webcam-index");
  const btnSrcRtsp = document.getElementById("btn-src-rtsp");
  const rtspUrlInput = document.getElementById("rtsp-url-input");

  // Helper for Authorization Headers on all API requests
  function authHeaders(extraHeaders = {}) {
    const headers = { ...extraHeaders };
    if (currentUserToken) {
      headers["Authorization"] = `Bearer ${currentUserToken}`;
    }
    if (currentUserId) {
      headers["X-User-ID"] = currentUserId;
      headers["X-Station-ID"] = currentUserId;
    }
    return headers;
  }

  // -----------------------------------------------------------
  // AUTHENTICATION & TAB NAVIGATION
  // -----------------------------------------------------------
  function switchAuthTab(tab) {
    if (tab === "signup") {
      tabBtnSignup.classList.add("active");
      tabBtnLogin.classList.remove("active");
      authPanelSignup.classList.remove("hidden");
      authPanelLogin.classList.add("hidden");
      authPanelQuick.classList.add("hidden");
      authPanelReset.classList.add("hidden");
    } else if (tab === "login") {
      tabBtnLogin.classList.add("active");
      tabBtnSignup.classList.remove("active");
      authPanelLogin.classList.remove("hidden");
      authPanelSignup.classList.add("hidden");
      authPanelQuick.classList.add("hidden");
      authPanelReset.classList.add("hidden");
    }
  }

  if (tabBtnLogin) tabBtnLogin.addEventListener("click", () => switchAuthTab("login"));
  if (tabBtnSignup) tabBtnSignup.addEventListener("click", () => switchAuthTab("signup"));
  if (linkToSignupFromLogin) linkToSignupFromLogin.addEventListener("click", () => switchAuthTab("signup"));
  if (linkToLoginFromSignup) linkToLoginFromSignup.addEventListener("click", () => switchAuthTab("login"));

  if (linkToQuickId) {
    linkToQuickId.addEventListener("click", () => {
      authPanelLogin.classList.add("hidden");
      authPanelSignup.classList.add("hidden");
      authPanelReset.classList.add("hidden");
      authPanelQuick.classList.remove("hidden");
    });
  }

  if (linkToLoginFromQuick) {
    linkToLoginFromQuick.addEventListener("click", () => switchAuthTab("login"));
  }

  if (linkToReset) {
    linkToReset.addEventListener("click", () => {
      authPanelLogin.classList.add("hidden");
      authPanelSignup.classList.add("hidden");
      authPanelQuick.classList.add("hidden");
      authPanelReset.classList.remove("hidden");
    });
  }

  if (linkToLoginFromReset) {
    linkToLoginFromReset.addEventListener("click", () => switchAuthTab("login"));
  }

  // -----------------------------------------------------------
  // INITIALIZE AUTH SYSTEM
  // -----------------------------------------------------------
  async function initAuthSystem() {
    try {
      const res = await fetch(`${API_BASE}/api/config/public`);
      if (res.ok) {
        const config = await res.json();
        authConfiguredOnServer = Boolean(config.auth_enabled && config.supabase_url && config.supabase_anon_key);

        if (authConfiguredOnServer && window.supabase) {
          supabaseClient = window.supabase.createClient(config.supabase_url, config.supabase_anon_key);
          const { data: { session } } = await supabaseClient.auth.getSession();
          if (session && session.user) {
            handleUserSignedIn(session.user.id, session.user.email, session.access_token);
            return;
          }

          supabaseClient.auth.onAuthStateChange((event, session) => {
            if (session && session.user) {
              handleUserSignedIn(session.user.id, session.user.email, session.access_token);
            }
          });
        }
      }
    } catch (err) {
      console.warn("[Auth] Public config check notice:", err);
    }

    // Check localStorage session
    const savedUserId = localStorage.getItem("cctv_user_id");
    const savedName = localStorage.getItem("cctv_display_name");
    const savedToken = localStorage.getItem("cctv_access_token");

    if (savedUserId && savedName) {
      handleUserSignedIn(savedUserId, savedName, savedToken);
    } else {
      showAuthGate();
    }
  }

  function handleUserSignedIn(userId, displayName, token = null) {
    currentUserId = userId || "default_user";
    currentUserDisplayName = displayName || "Store Manager";
    currentUserToken = token;

    localStorage.setItem("cctv_user_id", currentUserId);
    localStorage.setItem("cctv_display_name", currentUserDisplayName);
    if (token) localStorage.setItem("cctv_access_token", token);

    userDisplayName.textContent = currentUserDisplayName;
    userPill.classList.remove("hidden");
    hideAuthGate();

    // Reload stream and user CCTV details
    cctvStreamImg.src = `${API_BASE}/api/video_feed?t=${Date.now()}`;
    loadUserCctvDetails();
  }

  function handleUserLoggedOut() {
    if (supabaseClient) {
      supabaseClient.auth.signOut().catch(() => {});
    }
    currentUserToken = null;
    currentUserId = null;
    currentUserDisplayName = null;

    localStorage.removeItem("cctv_user_id");
    localStorage.removeItem("cctv_display_name");
    localStorage.removeItem("cctv_access_token");

    userPill.classList.add("hidden");
    showAuthGate();
    switchAuthTab("login");
  }

  function showAuthGate() {
    authGate.classList.remove("hidden");
    appDashboard.classList.add("hidden");
  }

  function hideAuthGate() {
    authGate.classList.add("hidden");
    appDashboard.classList.remove("hidden");
  }

  // -----------------------------------------------------------
  // CREATE ACCOUNT FOR FIRST-TIME USERS
  // -----------------------------------------------------------
  if (btnSignup) {
    btnSignup.addEventListener("click", async () => {
      const name = signupName.value.trim() || "Store Manager";
      const email = signupEmail.value.trim();
      const password = signupPassword.value.trim();
      const cctvName = signupCctvName.value.trim() || "Store CCTV Feed";

      authErrorSignup.classList.add("hidden");
      authSuccessSignup.classList.add("hidden");

      if (!email || !password) {
        authErrorSignup.textContent = "Please enter an email address and password.";
        authErrorSignup.classList.remove("hidden");
        return;
      }
      if (password.length < 6) {
        authErrorSignup.textContent = "Password must be at least 6 characters long.";
        authErrorSignup.classList.remove("hidden");
        return;
      }

      btnSignup.disabled = true;
      btnSignup.textContent = "Creating Account & Initializing CCTV...";

      try {
        // Register in backend (works locally + syncs with Supabase if configured)
        const res = await fetch(`${API_BASE}/api/auth/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password, display_name: name })
        });
        const data = await res.json();

        if (!res.ok || !data.success) {
          throw new Error(data.error || "Could not complete account creation.");
        }

        let authToken = null;
        if (supabaseClient) {
          try {
            const sbAuth = await supabaseClient.auth.signInWithPassword({ email, password });
            if (sbAuth.data?.session) {
              authToken = sbAuth.data.session.access_token;
            }
          } catch (_) {}
        }

        // Save their initial CCTV camera details
        const userId = data.user_id;
        await fetch(`${API_BASE}/api/user/cctv`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(authToken ? { "Authorization": `Bearer ${authToken}` } : { "X-User-ID": userId })
          },
          body: JSON.stringify({
            camera: { name: cctvName, source_type: "benchmark", config_data: {} }
          })
        }).catch(() => {});

        handleUserSignedIn(userId, name, authToken);
      } catch (err) {
        authErrorSignup.textContent = err.message || "Failed to create account.";
        authErrorSignup.classList.remove("hidden");
      } finally {
        btnSignup.disabled = false;
        btnSignup.textContent = "Create Account & Save CCTV Details";
      }
    });
  }

  // -----------------------------------------------------------
  // SIGN IN
  // -----------------------------------------------------------
  if (btnLogin) {
    btnLogin.addEventListener("click", async () => {
      const email = loginEmail.value.trim();
      const password = loginPassword.value.trim();
      authErrorLogin.classList.add("hidden");

      if (!email || !password) {
        authErrorLogin.textContent = "Please enter your email and password.";
        authErrorLogin.classList.remove("hidden");
        return;
      }

      btnLogin.disabled = true;
      btnLogin.textContent = "Signing in...";

      try {
        let userId = null;
        let displayName = email.split("@")[0];
        let authToken = null;

        // Try Supabase auth first if client initialized
        if (supabaseClient) {
          const { data, error } = await supabaseClient.auth.signInWithPassword({ email, password });
          if (!error && data?.session) {
            userId = data.session.user.id;
            displayName = data.session.user.user_metadata?.display_name || email;
            authToken = data.session.access_token;
          }
        }

        // Also authenticate with backend
        const res = await fetch(`${API_BASE}/api/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password })
        });
        const data = await res.json();

        if (res.ok && data.success) {
          userId = data.user_id || userId;
          displayName = data.display_name || displayName;
        } else if (!userId) {
          throw new Error(data.error || "Invalid credentials.");
        }

        handleUserSignedIn(userId, displayName, authToken);
      } catch (err) {
        authErrorLogin.textContent = err.message || "Sign in failed. Check your password or create an account.";
        authErrorLogin.classList.remove("hidden");
      } finally {
        btnLogin.disabled = false;
        btnLogin.textContent = "Sign In to Dashboard";
      }
    });
  }

  // Quick Station Login
  if (btnQuickLogin) {
    btnQuickLogin.addEventListener("click", () => {
      const name = quickUserName.value.trim() || "Front Checkout Station";
      handleUserSignedIn(`station_${Date.now()}`, name, null);
    });
  }

  // Password Reset
  if (btnReset) {
    btnReset.addEventListener("click", async () => {
      const email = resetEmail.value.trim();
      authErrorReset.classList.add("hidden");
      authSuccessReset.classList.add("hidden");

      if (!email) {
        authErrorReset.textContent = "Please enter your account email.";
        authErrorReset.classList.remove("hidden");
        return;
      }

      if (supabaseClient) {
        btnReset.disabled = true;
        btnReset.textContent = "Sending...";
        const { error } = await supabaseClient.auth.resetPasswordForEmail(email);
        btnReset.disabled = false;
        btnReset.textContent = "Send Reset Link";
        if (error) {
          authErrorReset.textContent = error.message;
          authErrorReset.classList.remove("hidden");
        } else {
          authSuccessReset.textContent = "Password reset instructions sent to your email.";
          authSuccessReset.classList.remove("hidden");
        }
      } else {
        authSuccessReset.textContent = "Reset request noted. In local mode, you can sign in directly or create a new profile.";
        authSuccessReset.classList.remove("hidden");
      }
    });
  }

  // Dashboard Logout Button
  if (btnLogout) {
    btnLogout.addEventListener("click", () => {
      if (confirm("Are you sure you want to log out of your CCTV account?")) {
        handleUserLoggedOut();
      }
    });
  }

  // -----------------------------------------------------------
  // LOAD & SAVE USER CCTV DETAILS
  // -----------------------------------------------------------
  async function loadUserCctvDetails() {
    try {
      const res = await fetch(`${API_BASE}/api/user/cctv`, {
        headers: authHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        if (data.camera) {
          if (data.camera.name) streamNameText.textContent = data.camera.name;
          if (data.camera.config_data?.url && rtspUrlInput) {
            rtspUrlInput.value = data.camera.config_data.url;
          }
          if (data.camera.config_data?.index !== undefined && webcamIndex) {
            webcamIndex.value = data.camera.config_data.index;
          }
        }
        if (data.regions) {
          currentRegions = data.regions;
          if (inputCheckoutName) inputCheckoutName.value = currentRegions.checkout?.name || "Main Checkout";
          if (inputShelfName) inputShelfName.value = currentRegions.shelf?.name || "Shelf 1";
        }
      }
    } catch (err) {
      console.warn("[CCTV Details] Notice loading user CCTV settings:", err);
    }
  }

  // -----------------------------------------------------------
  // REAL-TIME ANALYTICS POLLING (Features 1, 2, 3, 4)
  // -----------------------------------------------------------
  async function fetchAnalytics() {
    if (appDashboard.classList.contains("hidden")) return;

    try {
      const res = await fetch(`${API_BASE}/api/analytics`, { 
        cache: "no-store",
        headers: authHeaders()
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      updateDashboardUI(data);
      hideError();
    } catch (err) {
      showError(
        "Backend Disconnected",
        `Cannot connect to Python analytics server at ${API_BASE || 'http://127.0.0.1:5000'}. Ensure 'python run.py' is running.`
      );
    }
  }

  function updateDashboardUI(data) {
    const analytics = data.analytics || {};
    const source = data.source || {};

    // Source Status
    if (source.is_running) {
      videoSourcePill.className = "status-pill status-high";
      videoSourceText.textContent = "VIDEO SOURCE: Connected";
    } else {
      videoSourcePill.className = "status-pill status-unavail";
      videoSourceText.textContent = "VIDEO SOURCE: Disconnected";
    }
    if (source.actual_fps !== undefined) {
      streamFpsBadge.textContent = `${source.actual_fps.toFixed(1)} FPS`;
    }
    if (source.status_message && !streamNameText.textContent.includes("Store")) {
      streamNameText.textContent = source.status_message;
    }
    if (source.connection_error) {
      showError("Video Stream Notice", source.connection_error);
    }

    // FEATURE 1: CAMERA-WIDE PEOPLE COUNT (100% video frame)
    const f1 = analytics.people_count || {};
    f1PeopleCount.textContent = f1.display || "--";
    f1PeopleDesc.textContent = f1.label || "Analyzes the entire camera view independently";
    f1ReliabilityBadge.textContent = `Reliability: ${f1.reliability || 'High'}`;
    f1ReliabilityBadge.className = "badge-pill " + getBadgeClass(f1.reliability);
    const occPct = ((f1.occlusion_index || 0) * 100).toFixed(0);
    f1OcclusionText.textContent = `Cluster Overlap: ${occPct}%`;

    // FEATURE 2: CHECKOUT CONGESTION (User-defined region)
    const f2 = analytics.checkout || {};
    f2RegionName.textContent = `"${f2.region_name || 'Main Checkout'}"`;
    f2StatusText.textContent = f2.status || "Normal";
    f2StatusText.className = "status-indicator-text " + (f2.is_congested ? "color-alert" : "");
    f2PeopleCount.textContent = f2.visible_people !== undefined ? f2.visible_people : 0;
    f2Explanation.textContent = f2.explanation || "Monitoring user-defined checkout area.";
    f2ReliabilityBadge.textContent = `Reliability: ${f2.reliability || 'High'}`;
    f2ReliabilityBadge.className = "badge-pill " + getBadgeClass(f2.reliability);
    f2DwellText.textContent = `Congestion Dwell: ${f2.dwell_duration || 0}s`;

    // FEATURE 3: SHELF MONITOR (Obstruction gate strictly enforced)
    const f3 = analytics.shelf || {};
    f3RegionName.textContent = `"${f3.region_name || 'Shelf 1'}"`;
    f3StatusText.textContent = f3.status || "No significant visual change detected";
    if (f3.is_obstructed) {
      f3StatusText.className = "status-indicator-text color-obstructed";
    } else if (f3.is_changed) {
      f3StatusText.className = "status-indicator-text color-alert";
    } else {
      f3StatusText.className = "status-indicator-text";
    }
    f3ChangePct.textContent = `${f3.change_percentage || 0}%`;
    f3Explanation.textContent = f3.explanation || "Monitoring shelf region.";
    f3ReliabilityBadge.textContent = `Reliability: ${f3.reliability || 'High'}`;
    f3ReliabilityBadge.className = "badge-pill " + getBadgeClass(f3.reliability);

    // FEATURE 4: SYSTEM RELIABILITY
    const f4 = analytics.reliability || {};
    relVideoText.textContent = f4.video_quality || "Good";
    relPeopleText.textContent = f4.people_detection || "Reliable";
    relCheckoutText.textContent = f4.checkout_analysis || "Reliable";
    relShelfText.textContent = f4.shelf_analysis || "Reliable";

    setDotColor(dotVideo, f4.video_quality);
    setDotColor(dotPeople, f4.people_detection);
    setDotColor(dotCheckout, f4.checkout_analysis);
    setDotColor(dotShelf, f4.shelf_analysis);

    const isAllGood = (f4.video_quality === "Good" && f4.people_detection === "Reliable");
    f4OverallBadge.textContent = isAllGood ? "Operable" : "Caution";
    f4OverallBadge.className = "badge-pill " + (isAllGood ? "badge-success" : "badge-warning");
    
    if (f4.blur_score !== undefined) {
      relClarityScore.textContent = `Clarity Score: ${f4.blur_score.toFixed(1)} (${f4.blur_score > 35 ? 'Sharp' : 'Blurry'})`;
    }

    if (source.shelf_depleted_sim !== undefined) {
      btnToggleShelfSim.classList.toggle("btn-primary", source.shelf_depleted_sim);
      btnToggleShelfSim.textContent = source.shelf_depleted_sim ? "Reset Stocked" : "Simulate Shelf Change";
    }

    if (!modalAudit.classList.contains("hidden") && analytics.audit_trail) {
      auditLogContent.textContent = analytics.audit_trail.join("\n");
    }
  }

  function setDotColor(dotElem, statusText) {
    if (!dotElem) return;
    dotElem.className = "dot-indicator";
    if (statusText === "Good" || statusText === "Reliable") {
      dotElem.classList.add("dot-green");
    } else if (statusText === "Temporarily obstructed" || statusText === "Reduced") {
      dotElem.classList.add("dot-yellow");
    } else {
      dotElem.classList.add("dot-red");
    }
  }

  function getBadgeClass(rel) {
    if (rel === "High" || rel === "Reliable") return "badge-success";
    if (rel === "Medium" || rel === "Reduced") return "badge-warning";
    return "badge-danger";
  }

  // -----------------------------------------------------------
  // INTERACTIVE USER-DEFINED REGION DRAWING & CONFIGURATION
  // -----------------------------------------------------------
  let currentRegions = { checkout: {}, shelf: {} };
  let drawingTarget = null;
  let clickPoints = [];
  let ctx = null;

  async function loadRegions() {
    try {
      const res = await fetch(`${API_BASE}/api/config/regions`, {
        headers: authHeaders()
      });
      if (!res.ok) return;
      currentRegions = await res.json();
      if (inputCheckoutName) inputCheckoutName.value = currentRegions.checkout?.name || "Main Checkout";
      if (inputShelfName) inputShelfName.value = currentRegions.shelf?.name || "Shelf 1";
    } catch (err) {
      console.warn("Could not load regions config:", err);
    }
  }

  function startDrawingMode(target) {
    drawingTarget = target;
    clickPoints = [];
    modalRegions.classList.add("hidden");
    drawingToolbar.classList.remove("hidden");
    drawingCanvas.classList.remove("hidden");

    drawingCanvas.width = 640;
    drawingCanvas.height = 480;
    ctx = drawingCanvas.getContext("2d");
    redrawCanvas();
  }

  function stopDrawingMode() {
    drawingTarget = null;
    clickPoints = [];
    drawingToolbar.classList.add("hidden");
    drawingCanvas.classList.add("hidden");
  }

  function redrawCanvas() {
    if (!ctx) return;
    ctx.clearRect(0, 0, drawingCanvas.width, drawingCanvas.height);

    if (clickPoints.length > 0) {
      ctx.strokeStyle = drawingTarget === "CHECKOUT" ? "#c084fc" : "#fb923c";
      ctx.fillStyle = drawingTarget === "CHECKOUT" ? "rgba(192, 132, 252, 0.25)" : "rgba(251, 146, 60, 0.25)";
      ctx.lineWidth = 2;

      ctx.beginPath();
      ctx.moveTo(clickPoints[0].x, clickPoints[0].y);
      for (let i = 1; i < clickPoints.length; i++) {
        ctx.lineTo(clickPoints[i].x, clickPoints[i].y);
      }
      if (clickPoints.length >= 3) {
        ctx.closePath();
        ctx.fill();
      }
      ctx.stroke();

      for (const p of clickPoints) {
        ctx.fillStyle = "#ffffff";
        ctx.beginPath();
        ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  drawingCanvas.addEventListener("click", (e) => {
    if (!drawingTarget) return;
    const rect = drawingCanvas.getBoundingClientRect();
    const scaleX = drawingCanvas.width / rect.width;
    const scaleY = drawingCanvas.height / rect.height;

    const x = Math.round((e.clientX - rect.left) * scaleX);
    const y = Math.round((e.clientY - rect.top) * scaleY);

    clickPoints.push({ x, y });
    redrawCanvas();

    if (clickPoints.length === 4) {
      const polygon = clickPoints.map(p => [p.x, p.y]);
      if (drawingTarget === "CHECKOUT") {
        currentRegions.checkout = currentRegions.checkout || {};
        currentRegions.checkout.polygon = polygon;
        alert(`Checkout region coordinates captured! Click "Save Configuration" to commit.`);
      } else if (drawingTarget === "SHELF") {
        currentRegions.shelf = currentRegions.shelf || {};
        currentRegions.shelf.polygon = polygon;
        alert(`Shelf region coordinates captured! Click "Save Configuration" to commit.`);
      }
      stopDrawingMode();
      modalRegions.classList.remove("hidden");
    }
  });

  btnStartDrawCheckout.addEventListener("click", () => startDrawingMode("CHECKOUT"));
  btnStartDrawShelf.addEventListener("click", () => startDrawingMode("SHELF"));
  btnDrawCheckout.addEventListener("click", () => startDrawingMode("CHECKOUT"));
  btnDrawShelf.addEventListener("click", () => startDrawingMode("SHELF"));
  btnCancelDrawing.addEventListener("click", stopDrawingMode);

  btnEditCheckoutShortcut.addEventListener("click", () => modalRegions.classList.remove("hidden"));
  btnEditShelfShortcut.addEventListener("click", () => modalRegions.classList.remove("hidden"));

  btnSaveRegionNames.addEventListener("click", async () => {
    currentRegions.checkout = currentRegions.checkout || {};
    currentRegions.shelf = currentRegions.shelf || {};
    currentRegions.checkout.name = inputCheckoutName.value.trim() || "Main Checkout";
    currentRegions.shelf.name = inputShelfName.value.trim() || "Shelf 1";

    try {
      const res = await fetch(`${API_BASE}/api/config/regions`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(currentRegions),
      });
      const data = await res.json();
      alert("Configuration saved successfully!");
      modalRegions.classList.add("hidden");

      // Also persist to user CCTV configuration
      fetch(`${API_BASE}/api/user/cctv`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ regions: currentRegions })
      }).catch(() => {});
    } catch (err) {
      alert("Error saving regions: " + err.message);
    }
  });

  // Shelf Baseline Calibration
  async function triggerShelfCalibration() {
    try {
      const res = await fetch(`${API_BASE}/api/config/shelf/reset_baseline`, {
        method: "POST",
        headers: authHeaders()
      });
      const data = await res.json();
      if (data.success) {
        alert("Reference baseline successfully calibrated for Shelf Monitor!");
      } else {
        alert("Calibration warning: " + data.message);
      }
    } catch (err) {
      alert("Calibration request error: " + err.message);
    }
  }

  btnCalibrateShelf.addEventListener("click", triggerShelfCalibration);
  btnModalCalibrateShelf.addEventListener("click", triggerShelfCalibration);

  // -----------------------------------------------------------
  // CONTROLS & DISPLAY SETTINGS
  // -----------------------------------------------------------
  async function updateDisplaySettings() {
    const payload = {
      show_boxes: toggleBoxes.checked,
      show_regions: toggleRegions.checked,
      apply_privacy_blur: togglePrivacy.checked,
    };
    try {
      await fetch(`${API_BASE}/api/settings`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      });
    } catch (err) {
      console.warn("Settings update notice:", err);
    }
  }

  toggleBoxes.addEventListener("change", updateDisplaySettings);
  toggleRegions.addEventListener("change", updateDisplaySettings);
  togglePrivacy.addEventListener("change", updateDisplaySettings);

  btnToggleShelfSim.addEventListener("click", async () => {
    try {
      const res = await fetch(`${API_BASE}/api/sim/toggle_shelf`, {
        method: "POST",
        headers: authHeaders()
      });
      const data = await res.json();
      btnToggleShelfSim.classList.toggle("btn-primary", data.shelf_depleted);
      btnToggleShelfSim.textContent = data.shelf_depleted ? "Reset Stocked" : "Simulate Shelf Change";
    } catch (err) {
      console.warn("Toggle shelf error:", err);
    }
  });

  // -----------------------------------------------------------
  // VIDEO SOURCE SWITCHING CONTROLS
  // -----------------------------------------------------------
  btnSrcBenchmark.addEventListener("click", async () => {
    try {
      await fetch(`${API_BASE}/api/source/benchmark`, {
        method: "POST",
        headers: authHeaders()
      });
      streamNameText.textContent = "Built-in Store CCTV Simulation";
      modalSource.classList.add("hidden");
    } catch (err) {
      alert("Source switch error: " + err);
    }
  });

  btnSrcWebcam.addEventListener("click", async () => {
    const idx = parseInt(webcamIndex.value) || 0;
    try {
      const res = await fetch(`${API_BASE}/api/source/webcam`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ index: idx }),
      });
      const data = await res.json();
      if (!data.success) {
        alert("Webcam error: " + (data.source?.connection_error || "Device not found"));
      } else {
        streamNameText.textContent = `USB Webcam (Device ${idx})`;
        modalSource.classList.add("hidden");
      }
    } catch (err) {
      alert("Webcam request error: " + err);
    }
  });

  btnSrcRtsp.addEventListener("click", async () => {
    const url = rtspUrlInput.value.trim();
    if (!url) {
      alert("Please enter a valid RTSP stream URL.");
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/source/rtsp`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ url }),
      });
      const data = await res.json();
      if (!data.success) {
        alert("RTSP connection notice:\n\n" + (data.source?.connection_error || data.error));
      } else {
        streamNameText.textContent = "RTSP IP Camera Stream";
        modalSource.classList.add("hidden");
      }
    } catch (err) {
      alert("RTSP error: " + err);
    }
  });

  btnUploadFile.addEventListener("click", async () => {
    const file = videoFileInput.files[0];
    if (!file) {
      alert("Please select a video file to upload.");
      return;
    }
    const formData = new FormData();
    formData.append("video_file", file);

    btnUploadFile.disabled = true;
    btnUploadFile.textContent = "Uploading...";

    try {
      const res = await fetch(`${API_BASE}/api/source/upload`, {
        method: "POST",
        headers: authHeaders(),
        body: formData,
      });
      const data = await res.json();
      btnUploadFile.disabled = false;
      btnUploadFile.textContent = "Upload & Stream";

      if (!res.ok || !data.success) {
        alert("Video upload notice:\n\n" + (data.error || "Upload failed"));
      } else {
        alert(`Successfully loaded "${data.filename}". Stream active.`);
        streamNameText.textContent = `Video: ${data.filename}`;
        modalSource.classList.add("hidden");
      }
    } catch (err) {
      btnUploadFile.disabled = false;
      btnUploadFile.textContent = "Upload & Stream";
      alert(
        `Upload Failed: ${err.message || err}\n\n` +
        `Ensure 'python run.py' is running.`
      );
    }
  });

  // -----------------------------------------------------------
  // MODALS & BANNER DISMISS
  // -----------------------------------------------------------
  btnOpenRegions.addEventListener("click", () => modalRegions.classList.remove("hidden"));
  btnOpenSource.addEventListener("click", () => modalSource.classList.remove("hidden"));
  btnOpenAudit.addEventListener("click", () => modalAudit.classList.remove("hidden"));

  modalCloseBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      modalRegions.classList.add("hidden");
      modalSource.classList.add("hidden");
      modalAudit.classList.add("hidden");
    });
  });

  bannerDismiss.addEventListener("click", hideError);

  function showError(title, msg) {
    errorBanner.classList.remove("hidden");
    bannerTitle.textContent = title;
    bannerMsg.textContent = msg;
  }

  function hideError() {
    errorBanner.classList.add("hidden");
  }

  // -----------------------------------------------------------
  // APP BOOTSTRAP
  // -----------------------------------------------------------
  initAuthSystem();
  setInterval(fetchAnalytics, 1000);
});
