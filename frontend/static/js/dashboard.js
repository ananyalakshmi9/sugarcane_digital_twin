// Sugarcane Digital Twin Platform — Dashboard Script
let varietiesList = [];
let farmsList = [];
let pullMap = null;
let pullCircle = null;
let pullPolygon = null;
let pullMarker = null;
let pullVertices = [];
let pullPointMarkers = [];
let rawMap = null;
let rawMarker = null;
let rawVertices = [];
let rawPointMarkers = [];
let rawPolygon = null;
let lastAnalyzedPlan = null;

// --- Page routing & tab switching ---
function switchPage(pageId) {
    document.querySelectorAll('.page').forEach(page => {
        page.classList.remove('active');
    });
    const targetPage = document.getElementById('page-' + pageId);
    if (targetPage) {
        targetPage.classList.add('active');
    }

    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.remove('active');
    });

    const activeLink = Array.from(document.querySelectorAll('.nav-link')).find(el => {
        const onclickAttr = el.getAttribute('onclick');
        return onclickAttr && onclickAttr.includes(pageId);
    });
    if (activeLink) {
        activeLink.classList.add('active');
    }

    sessionStorage.setItem('active_page', pageId);

    // Custom page-specific renderings
    if (pageId === 'dashboard') {
        loadDashboardStats();
    } else if (pageId === 'ideal') {
        renderBaselineCurves();
        initRawMap();
        setTimeout(() => {
            if (rawMap) rawMap.invalidateSize();
        }, 100);
    } else if (pageId === 'puller') {
        initPullMap();
        setTimeout(() => {
            if (pullMap) {
                pullMap.invalidateSize();
                updatePullMapCircle();
            }
        }, 100);
    }
}

// Initialise inputs and drop-down selectors
window.addEventListener('DOMContentLoaded', () => {
    loadVarieties();
    loadFarms();

    // Autocomplete/autofill for current twin extractor
    const pullFarmIdInput = document.getElementById('pull-farm-id-input');
    if (pullFarmIdInput) {
        pullFarmIdInput.addEventListener('input', () => {
            const val = pullFarmIdInput.value.trim();
            const hiddenId = document.getElementById('pull-farm-id');
            if (hiddenId) hiddenId.value = val;
            if (val === '') {
                window.lastAutofilledFarmId = '';
            }
            autoFillFarmDetails();
        });
    }

    const pullLat = document.getElementById('pull-lat');
    const pullLon = document.getElementById('pull-lon');
    const pullAcres = document.getElementById('pull-acres');
    if (pullLat) pullLat.addEventListener('input', () => {
        window.currentPullBoundary = null;
        updatePullMapCircle();
    });
    if (pullLon) pullLon.addEventListener('input', () => {
        window.currentPullBoundary = null;
        updatePullMapCircle();
    });
    if (pullAcres) pullAcres.addEventListener('input', () => {
        window.currentPullBoundary = null;
        updatePullMapCircle();
    });

    // Page switcher fallback
    const activePage = sessionStorage.getItem('active_page') || 'dashboard';
    switchPage(activePage);
});

function loadVarieties() {
    fetch('/api/config/varieties')
        .then(res => res.json())
        .then(data => {
            varietiesList = data;

            // 1. Render registry rows
            const tblBody = document.getElementById('tbl-varieties-body');
            if (tblBody) {
                tblBody.innerHTML = '';
                data.forEach(v => {
                    const tr = document.createElement('tr');
                    const badgeClass = v.status === 'active' ? 'badge-active' : (v.status === 'draft' ? 'badge-draft' : 'badge-inactive');

                    tr.innerHTML = `
                        <td style="font-weight:700; color:var(--dark-green);">${v.variety}</td>
                        <td>${v.name}</td>
                        <td>${v.lifecycle_days} Days</td>
                        <td><span class="badge ${badgeClass}">${v.status}</span></td>
                        <td>${v.notes || 'N/A'}</td>
                    `;
                    tblBody.appendChild(tr);
                });
            }

            // 2. Populate live puller options
            const varietyOpts = document.getElementById('variety-select-opts');
            if (varietyOpts) {
                varietyOpts.innerHTML = '';
                data.forEach(v => {
                    if (v.status !== 'inactive') {
                        const div = document.createElement('div');
                        div.className = 'search-select-option';
                        div.innerText = `${v.variety} — ${v.name}`;
                        div.onclick = () => selectOption('variety', v.variety, `${v.variety} — ${v.name}`);
                        varietyOpts.appendChild(div);
                    }
                });
            }

            // 3. Populate baseline curves variety select dynamically
            const curvesSelect = document.getElementById('sel-variety-curves');
            if (curvesSelect) {
                const currentVal = curvesSelect.value;
                curvesSelect.innerHTML = '';
                data.forEach(v => {
                    if (v.status !== 'inactive') {
                        const opt = document.createElement('option');
                        opt.value = v.variety;
                        opt.textContent = `${v.variety} — ${v.name}`;
                        curvesSelect.appendChild(opt);
                    }
                });
                if (currentVal && data.some(v => v.variety === currentVal)) {
                    curvesSelect.value = currentVal;
                }
            }
        });
}

function loadFarms() {
    fetch('/api/farms')
        .then(res => res.json())
        .then(data => {
            farmsList = data;

            const farmOpts = document.getElementById('farm-select-opts');
            if (farmOpts) {
                farmOpts.innerHTML = '';
                data.forEach(f => {
                    const div = document.createElement('div');
                    div.className = 'search-select-option';
                    div.innerText = `Farm ${f.farm_id} (${f.farmer_name}) — ${f.variety}`;
                    div.onclick = () => selectOption('farm', f.farm_id, `Farm ${f.farm_id} (${f.farmer_name})`, f.variety);
                    farmOpts.appendChild(div);
                });
            }

            const pullFarmOpts = document.getElementById('pull-farm-select-opts');
            if (pullFarmOpts) {
                pullFarmOpts.innerHTML = '';
                data.forEach(f => {
                    const div = document.createElement('div');
                    div.className = 'search-select-option';
                    div.innerText = `Farm ${f.farm_id} (${f.farmer_name}) — ${f.variety}`;
                    div.onclick = () => selectOption('pull-farm', f.farm_id, `Farm ${f.farm_id} (${f.farmer_name})`, f.variety);
                    pullFarmOpts.appendChild(div);
                });
            }
        });
}

function autoFillFarmDetails() {
    const farmId = document.getElementById('pull-farm-id').value.trim();
    if (!farmId) return;
    
    // Check if we already queried this recently to avoid double-requesting
    if (window.lastAutofilledFarmId === farmId) return;
    window.lastAutofilledFarmId = farmId;
    
    // Clear manual drawing state before autofill
    pullPointMarkers.forEach(marker => {
        if (pullMap && marker) {
            pullMap.removeLayer(marker);
        }
    });
    pullPointMarkers = [];
    pullVertices = [];
    if (pullPolygon && pullMap) {
        pullMap.removeLayer(pullPolygon);
        pullPolygon = null;
    }
    if (pullCircle && pullMap) {
        pullMap.removeLayer(pullCircle);
        pullCircle = null;
    }
    
    fetch(`/api/farm/${encodeURIComponent(farmId)}`)
        .then(res => res.json())
        .then(data => {
            if (data && (data.latitude || data.longitude || data.planting_date)) {
                if (data.latitude) document.getElementById('pull-lat').value = data.latitude;
                if (data.longitude) document.getElementById('pull-lon').value = data.longitude;
                if (data.area_acres) document.getElementById('pull-acres').value = data.area_acres;
                if (data.planting_date) document.getElementById('pull-planting-date').value = data.planting_date;
                
                // Select variety
                if (data.variety) {
                    const selectVal = data.variety;
                    document.getElementById('pull-variety-val').value = selectVal;
                    document.getElementById('pull-variety-input').value = selectVal;
                }
                
                // Re-create pullMarker if it was deleted during drawing
                if (!pullMarker && pullMap) {
                    pullMarker = L.marker([parseFloat(data.latitude) || 20.78991, parseFloat(data.longitude) || 74.13846], { draggable: true }).addTo(pullMap);
                    pullMarker.on('dragend', function (e) {
                        const position = pullMarker.getLatLng();
                        const latInput2 = document.getElementById('pull-lat');
                        const lonInput2 = document.getElementById('pull-lon');
                        if (latInput2) latInput2.value = parseFloat(position.lat).toFixed(5);
                        if (lonInput2) lonInput2.value = parseFloat(position.lng).toFixed(5);
                        updatePullMapCircle();
                    });
                }
                
                window.currentPullBoundary = data.boundary;
                updatePullMapCircle();
            }
        })
        .catch(err => console.error('Error autofilling farm details:', err));
}

// --- OPTION SELECT INPUT HANDLERS ---
function showOptions(type) {
    const container = document.getElementById(type + '-select-opts');
    if (container) container.style.display = 'block';
    
    const wrapper = document.getElementById(type + '-select-container');
    if (wrapper) wrapper.style.zIndex = '1100';
}

// Close list options on outside clicks
document.addEventListener('click', (e) => {
    const varCont = document.getElementById('variety-select-container');
    if (varCont && !varCont.contains(e.target)) {
        const opts = document.getElementById('variety-select-opts');
        if (opts) opts.style.display = 'none';
        varCont.style.zIndex = '';
    }

    const farmCont = document.getElementById('farm-select-container');
    if (farmCont && !farmCont.contains(e.target)) {
        const opts = document.getElementById('farm-select-opts');
        if (opts) opts.style.display = 'none';
        farmCont.style.zIndex = '';
    }

    const pullFarmCont = document.getElementById('pull-farm-select-container');
    if (pullFarmCont && !pullFarmCont.contains(e.target)) {
        const opts = document.getElementById('pull-farm-select-opts');
        if (opts) opts.style.display = 'none';
        pullFarmCont.style.zIndex = '';
    }
});

function filterOptions(type) {
    let inputId = '';
    if (type === 'variety') {
        inputId = 'pull-variety-input';
    } else if (type === 'farm') {
        inputId = 'analyze-farm-input';
    } else if (type === 'pull-farm') {
        inputId = 'pull-farm-id-input';
    }
    const input = document.getElementById(inputId);
    const optsDiv = document.getElementById(type + '-select-opts');
    if (!input || !optsDiv) return;

    const val = input.value.toLowerCase();
    const options = optsDiv.getElementsByClassName('search-select-option');
    for (let opt of options) {
        opt.style.display = opt.innerText.toLowerCase().includes(val) ? 'block' : 'none';
    }
}

function selectOption(type, val, label, extra = null) {
    const wrapper = document.getElementById(type + '-select-container');
    if (wrapper) wrapper.style.zIndex = '';

    if (type === 'variety') {
        document.getElementById('pull-variety-input').value = label;
        document.getElementById('pull-variety-val').value = val;
        document.getElementById('variety-select-opts').style.display = 'none';
    } else if (type === 'farm') {
        document.getElementById('analyze-farm-input').value = label;
        document.getElementById('analyze-farm-val').value = val;
        document.getElementById('analyze-variety-val').value = extra;
        document.getElementById('farm-select-opts').style.display = 'none';
    } else if (type === 'pull-farm') {
        document.getElementById('pull-farm-id-input').value = label;
        document.getElementById('pull-farm-id').value = val;
        document.getElementById('pull-farm-select-opts').style.display = 'none';
        autoFillFarmDetails();
    }
}

// --- SUBMIT OPERATIONS ---
function submitRawFarm(event) {
    event.preventDefault();
    document.getElementById('loader-raw-farm').style.display = 'flex';
    
    const payload = {
        farm_id: document.getElementById('raw-farm-id').value.trim(),
        farmer_name: document.getElementById('raw-farmer-name').value.trim(),
        year: document.getElementById('raw-year').value.trim(),
        village: document.getElementById('raw-village').value.trim(),
        variety: document.getElementById('raw-variety').value,
        crop_type: document.getElementById('raw-crop-type').value,
        latitude: document.getElementById('raw-lat').value,
        longitude: document.getElementById('raw-lon').value,
        area_acres: document.getElementById('raw-area-acres').value,
        planting_date: document.getElementById('raw-planting-date').value.trim(),
        harvest_date: document.getElementById('raw-harvest-date').value.trim(),
        yield_achieved: document.getElementById('raw-yield-achieved').value,
        soil_type: document.getElementById('raw-soil-type').value.trim(),
        land_prep: document.getElementById('raw-land-prep').value.trim(),
        incident: document.getElementById('raw-incident').value.trim(),
        total_cost: document.getElementById('raw-total-cost').value,
        total_revenue: document.getElementById('raw-total-revenue').value,
        irrigation_type: document.getElementById('raw-irrigation-type').value,
        irrigation_interval_veg: document.getElementById('raw-irrigation-veg').value,
        irrigation_interval_rep: document.getElementById('raw-irrigation-rep').value,
        fertigation: document.getElementById('raw-fertigation').value.trim(),
        fertilizer_application: document.getElementById('raw-fertilizer-app').value.trim(),
        pgr: document.getElementById('raw-pgr').value.trim(),
        micronutrients: document.getElementById('raw-micronutrients').value.trim(),
        soil_health: document.getElementById('raw-soil-health').value.trim(),
        humic_acid: document.getElementById('raw-humic-acid').value.trim(),
        multi_nutrient: document.getElementById('raw-multi-nutrient').value.trim(),
        seaweed_extract: document.getElementById('raw-seaweed-extract').value.trim(),
        biofertilizers: document.getElementById('raw-biofertilizers').value.trim(),
        biocontrol_agents: document.getElementById('raw-biocontrol-agents').value.trim(),
        biopesticide: document.getElementById('raw-biopesticide').value.trim(),
        amino_acids: document.getElementById('raw-amino-acids').value.trim(),
        special_practices: document.getElementById('raw-special-practices').value.trim(),
        brix: document.getElementById('raw-brix').value,
        ccs: document.getElementById('raw-ccs').value,
        boundary: rawVertices.length >= 3 ? rawVertices.map(v => ({ lat: v[0], lng: v[1] })) : null
    };
    
    fetch('/api/raw-farm/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        document.getElementById('loader-raw-farm').style.display = 'none';
        if (data.status === 'success') {
            alert(data.message);
            document.getElementById('form-add-raw-farm').reset();
            clearRawMap();
            loadFarms(); // Reload farms dropdown list
        } else {
            alert('Error: ' + data.message);
        }
    })
    .catch(err => {
        document.getElementById('loader-raw-farm').style.display = 'none';
        alert('Request failed: ' + err.toString());
    });
}

function regenerateBaselines() {
    document.getElementById('loader-registry').style.display = 'flex';
    const logBox = document.getElementById('regenerate-logs');
    if (logBox) logBox.innerHTML = '<div class="console-line console-success">Initializing Ideal Twin baseline calculations...</div>';

    fetch('/api/ideal-twin/regenerate', { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            document.getElementById('loader-registry').style.display = 'none';

            if (logBox) {
                // Populate lines
                logBox.innerHTML = '';
                data.logs.split('\n').forEach(line => {
                    const div = document.createElement('div');
                    div.className = 'console-line' + (line.includes('failed') || line.includes('Error') ? ' console-error' : (line.includes('Success') || line.includes('Created') ? ' console-success' : ''));
                    div.innerText = line;
                    logBox.appendChild(div);
                });
            }

            if (data.status === 'success') {
                alert('Baselines successfully regenerated.');
                renderBaselineCurves(); // Refresh graphs
            } else {
                alert('Failed to regenerate twins: ' + data.message);
            }
        })
        .catch(err => {
            document.getElementById('loader-registry').style.display = 'none';
            if (logBox) logBox.innerHTML = `<div class="console-line console-error">${err.toString()}</div>`;
        });
}

function pullLiveDetails(e) {
    e.preventDefault();
    document.getElementById('loader-puller').style.display = 'flex';
    updatePipelineWorkflow('extraction', 1);

    const logBox = document.getElementById('pull-logs');
    if (logBox) logBox.innerHTML = '<div class="console-line">Contacting GEE pipeline endpoints...</div>';

    let varietyVal = document.getElementById('pull-variety-val').value;
    if (!varietyVal) {
        const inputVal = document.getElementById('pull-variety-input').value.trim();
        varietyVal = inputVal.split(' ')[0].split('—')[0].trim().toUpperCase().replace(/ /g, '_');
    }

    const payload = {
        farm_id: document.getElementById('pull-farm-id').value.trim(),
        latitude: document.getElementById('pull-lat').value,
        longitude: document.getElementById('pull-lon').value,
        field_area_acres: document.getElementById('pull-acres').value,
        variety: varietyVal,
        planting_date: document.getElementById('pull-planting-date').value.trim(),
        boundary: pullVertices.length >= 3 ? pullVertices.map(v => ({ lat: v[0], lng: v[1] })) : (window.currentPullBoundary || null)
    };

    fetch('/api/live-twin/pull', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
        .then(res => res.json())
        .then(data => {
            document.getElementById('loader-puller').style.display = 'none';
            if (data.status === 'success') {
                updatePipelineWorkflow('extraction', 7); // Final state
                if (logBox) logBox.innerHTML = `<div class="console-line console-success">${data.message}</div><div class="console-line">Output file written to: ${data.output_path}</div>`;
                alert('Live data pull completed successfully.');
                loadFarms(); // Reload list
            } else {
                updatePipelineWorkflow('extraction', 1);
                if (logBox) logBox.innerHTML = `<div class="console-line console-error">Pull failed: ${data.message}</div><div class="console-line console-error">${data.details || ''}</div>`;
                alert('Error pulling GEE details: ' + data.message);
            }
        })
        .catch(err => {
            document.getElementById('loader-puller').style.display = 'none';
            updatePipelineWorkflow('extraction', 1);
            if (logBox) logBox.innerHTML = `<div class="console-line console-error">${err.toString()}</div>`;
        });
}

function runGapAnalysis() {
    let farmId = document.getElementById('analyze-farm-val').value;
    let variety = document.getElementById('analyze-variety-val').value;

    if (!farmId) {
        const inputVal = document.getElementById('analyze-farm-input').value.trim();
        const match = inputVal.match(/Farm\s+([^\s(]+)/i) || inputVal.match(/^([^\s(]+)/);
        farmId = match ? match[1] : inputVal;
    }

    if (farmId && !variety) {
        const found = farmsList.find(f => String(f.farm_id) === String(farmId));
        if (found) {
            variety = found.variety;
        }
    }

    if (!farmId || !variety) {
        alert('Please select or enter a valid farm to analyze.');
        return;
    }

    document.getElementById('loader-analysis').style.display = 'flex';

    fetch('/api/live-twin/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ farm_id: farmId, variety: variety })
    })
        .then(res => res.json())
        .then(data => {
            document.getElementById('loader-analysis').style.display = 'none';
            if (data.status === 'success') {
                document.getElementById('analysis-results').style.display = 'flex';
                document.getElementById('conclusion-results').style.display = 'flex';

                lastAnalyzedPlan = data.plan;

                renderGapReport(data.plan);
                renderConclusion(data.plan);
            } else {
                alert('Error executing gap analysis: ' + data.message);
            }
        })
        .catch(err => {
            document.getElementById('loader-analysis').style.display = 'none';
            alert('Analysis runtime failed: ' + err.toString());
        });
}

    // Page 1: Dashboard Radial Universe
    function renderFarmUniverse(healthy = 0, watch = 0, critical = 0, total = 0, varieties = 0) {
        const container = document.getElementById('farm-universe');
        if (!container) return;

        container.innerHTML = `
        <svg viewBox="0 0 400 320" class="universe-svg">
            <!-- Center Core -->
            <line x1="200" y1="160" x2="80" y2="100" class="universe-line" />
            <line x1="200" y1="160" x2="320" y2="100" class="universe-line" />
            <line x1="200" y1="160" x2="200" y2="270" class="universe-line" />
            <line x1="200" y1="160" x2="300" y2="230" class="universe-line" />
            
            <circle cx="200" cy="160" r="45" class="universe-center" />
            <text x="200" y="156" text-anchor="middle" font-size="16" font-weight="800" fill="var(--dark-green)">${total}</text>
            <text x="200" y="172" text-anchor="middle" font-size="9" font-weight="700" fill="var(--muted-text)" letter-spacing="0.5">FARMS</text>
            
            <!-- Orbit lines -->
            <circle cx="200" cy="160" r="110" class="universe-orbit" />
            
            <!-- Nodes -->
            <!-- Healthy -->
            <g class="universe-node" onclick="switchPage('analysis')">
                <circle cx="80" cy="100" r="28" fill="#FFFFFF" stroke="var(--primary-green)" stroke-width="2" />
                <circle cx="80" cy="100" r="23" fill="var(--light-green)" opacity="0.4" />
                <text x="80" y="97" text-anchor="middle" font-size="11" font-weight="700" fill="var(--dark-green)">${healthy}</text>
                <text x="80" y="110" text-anchor="middle" font-size="7" font-weight="700" fill="var(--muted-text)">HEALTHY</text>
            </g>
            
            <!-- Watch -->
            <g class="universe-node" onclick="switchPage('analysis')">
                <circle cx="320" cy="100" r="28" fill="#FFFFFF" stroke="var(--primary-green)" stroke-width="2" />
                <circle cx="320" cy="100" r="23" fill="var(--light-green)" opacity="0.6" />
                <text x="320" y="97" text-anchor="middle" font-size="11" font-weight="700" fill="var(--dark-green)">${watch}</text>
                <text x="320" y="110" text-anchor="middle" font-size="7" font-weight="700" fill="var(--muted-text)">WATCH</text>
            </g>
            
            <!-- Critical -->
            <g class="universe-node" onclick="switchPage('analysis')">
                <circle cx="200" cy="270" r="28" fill="#FFFFFF" stroke="var(--critical-red)" stroke-width="1.5" />
                <circle cx="200" cy="270" r="23" fill="rgba(220,38,38,0.06)" />
                <text x="200" y="267" text-anchor="middle" font-size="11" font-weight="700" fill="var(--critical-red)">${critical}</text>
                <text x="200" y="280" text-anchor="middle" font-size="7" font-weight="700" fill="var(--muted-text)">CRITICAL</text>
            </g>
 
            <!-- Active varieties -->
            <g class="universe-node" onclick="switchPage('ideal')">
                <circle cx="300" cy="230" r="26" fill="#FFFFFF" stroke="var(--primary-green)" stroke-width="1.5" />
                <text x="300" y="227" text-anchor="middle" font-size="10" font-weight="700" fill="var(--dark-green)">${varieties}</text>
                <text x="300" y="238" text-anchor="middle" font-size="7" font-weight="700" fill="var(--muted-text)">VARIETIES</text>
            </g>
        </svg>
    `;
    }

    // Page 1: Donut Chart
    function renderDonutChart(healthyPct = 74, watchPct = 18, criticalPct = 8) {
        const container = document.getElementById('donut-chart');
        if (!container) return;

        const circumference = 345;
        const watchStroke = Math.round((watchPct / 100) * circumference);
        const criticalStroke = Math.round((criticalPct / 100) * circumference);
        const healthyStroke = circumference - watchStroke - criticalStroke;

        container.innerHTML = `
        <svg viewBox="0 0 160 160" width="130" height="130">
            <!-- Healthy -->
            <circle cx="80" cy="80" r="55" fill="none" stroke="var(--light-green)" stroke-width="20" />
            <!-- Watch -->
            <circle cx="80" cy="80" r="55" fill="none" stroke="var(--primary-green)" stroke-width="20" stroke-dasharray="${watchStroke} ${circumference}" stroke-dashoffset="-${healthyStroke}" />
            <!-- Critical -->
            <circle cx="80" cy="80" r="55" fill="none" stroke="var(--dark-green)" stroke-width="20" stroke-dasharray="${criticalStroke} ${circumference}" stroke-dashoffset="-${healthyStroke + watchStroke}" />
            
            <circle cx="80" cy="80" r="40" fill="#FFFFFF" />
            <text x="80" y="85" text-anchor="middle" font-size="14" font-weight="800" fill="var(--text)">${healthyPct}%</text>
        </svg>
    `;
    }

    // Page 1: Stats Loader
    function loadDashboardStats() {
        // Render placeholders first
        renderFarmUniverse('--', '--', '--', '--', '--');
        renderDonutChart(0, 0, 0);

        fetch('/api/dashboard/stats')
            .then(res => res.json())
            .then(data => {
                renderFarmUniverse(data.healthy_count, data.watch_count, data.critical_count, data.total_farms, data.varieties_count);

                const subtitleSpan = document.getElementById('lbl-total-farms-subtitle');
                if (subtitleSpan) {
                    subtitleSpan.textContent = data.total_farms;
                }

                const total = data.total_farms || 1;
                const healthyPct = Math.round((data.healthy_count / total) * 100);
                const watchPct = Math.round((data.watch_count / total) * 100);
                const criticalPct = Math.max(0, 100 - healthyPct - watchPct);

                renderDonutChart(healthyPct, watchPct, criticalPct);

                const legendLabels = document.querySelectorAll('.donut-legend span');
                if (legendLabels.length >= 3) {
                    legendLabels[0].textContent = `Healthy (${healthyPct}%)`;
                    legendLabels[1].textContent = `Watch (${watchPct}%)`;
                    legendLabels[2].textContent = `Critical (${criticalPct}%)`;
                }

                const tblBody = document.querySelector('#page-dashboard table tbody');
                if (tblBody) {
                    tblBody.innerHTML = '';
                    data.top_risk_farms.forEach(f => {
                        const tr = document.createElement('tr');

                        const healthPct = f.health_score;
                        let badgeClass = 'badge-active';
                        if (healthPct < 40) {
                            badgeClass = 'badge-critical';
                        } else if (healthPct < 75) {
                            badgeClass = 'badge-draft';
                        }

                        tr.innerHTML = `
                        <td style="font-weight:700; color:var(--dark-green);">${f.farm_id}</td>
                        <td><span class="badge ${badgeClass}">${Math.round(healthPct)}% Health</span></td>
                        <td>${f.primary_issue}</td>
                        <td>${f.last_updated}</td>
                        <td>${f.action_required}</td>
                    `;
                        tblBody.appendChild(tr);
                    });
                }
            })
            .catch(err => console.error("Error loading dashboard stats:", err));
    }

    // Math coordinate scaler for dynamic SVGs
    function getSVGPath(dapArray, meanArray, width, height) {
        if (!dapArray || !meanArray || dapArray.length === 0) return { path: '', fillPath: '' };

        const minDap = Math.min(...dapArray);
        const maxDap = Math.max(...dapArray);

        const minMean = Math.min(...meanArray);
        const maxMean = Math.max(...meanArray);

        const rangeDap = maxDap - minDap || 1;
        const rangeMean = maxMean - minMean || 1;

        let points = [];
        for (let i = 0; i < dapArray.length; i++) {
            const x = ((dapArray[i] - minDap) / rangeDap) * width;
            const y = height - ((meanArray[i] - minMean) / rangeMean) * height;
            points.push(`${x.toFixed(1)},${y.toFixed(1)}`);
        }

        const path = `M ${points.join(' L ')}`;
        const fillPath = `${path} L ${width.toFixed(1)},${height.toFixed(1)} L 0,${height.toFixed(1)} Z`;

        return { path, fillPath };
    }

    // Page 2: Ideal Twin Baseline Curves
    function renderBaselineCurves() {
        const container = document.getElementById('baseline-curves');
        if (!container) return;

        const selVariety = document.getElementById('sel-variety-curves')?.value || '8005';
        container.innerHTML = '<div style="grid-column:1/-1; text-align:center; padding:40px; color:var(--muted-text);">Loading real index curves...</div>';

        fetch(`/api/ideal-twin/curves?variety=${selVariety}`)
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    container.innerHTML = `
                    <div style="grid-column:1/-1; text-align:center; padding:48px 24px; border: 1px dashed var(--border); border-radius: var(--radius-sm); background-color: var(--section-bg);">
                        <div style="font-size:14px; font-weight:600; color:var(--text); margin-bottom:6px;">No Baseline Curves Available</div>
                        <div style="font-size:12px; color:var(--muted-text); max-width:400px; margin:0 auto;">${data.error}</div>
                    </div>`;
                    return;
                }

                container.innerHTML = '';

                // Loop through each index curve returned
                for (let idx in data.curves) {
                    const curveData = data.curves[idx];
                    const dap = curveData.dap;
                    const mean = curveData.mean;

                    if (!dap || !mean || dap.length === 0) continue;

                    const div = document.createElement('div');
                    div.className = 'curve-card';

                    const { path, fillPath } = getSVGPath(dap, mean, 320, 90);

                    let color = 'var(--primary-green)';
                    if (idx === 'NDWI') {
                        color = '#06B6D4';
                    } else if (idx.includes('temp') || idx.includes('wind') || idx.includes('precip')) {
                        color = 'var(--dark-green)';
                    }

                    div.innerHTML = `
                    <div style="display:flex; justify-content:space-between; font-weight:700; font-size:13px; color:var(--dark-green); margin-bottom:8px;">
                        <span>${idx} Baseline</span>
                        <span style="font-size:11px; font-weight:500; color:var(--muted-text);">Range: ${Math.min(...mean).toFixed(2)} to ${Math.max(...mean).toFixed(2)}</span>
                    </div>
                    <svg class="curve-svg" viewBox="0 0 320 95" style="height:95px; width:100%;">
                        <!-- Shaded 2-sigma area -->
                        <path d="${fillPath}" fill="${color}" fill-opacity="0.08" />
                        <!-- Mean Line -->
                        <path d="${path}" fill="none" stroke="${color}" stroke-width="2" />
                    </svg>
                `;
                    container.appendChild(div);
                }
            })
            .catch(err => {
                container.innerHTML = `<div style="grid-column:1/-1; text-align:center; padding:40px; color:var(--critical-red);">Failed to load baseline curves: ${err.toString()}</div>`;
            });
    }

    // Page 3: Horizontal Pipeline Workflow Animation
    function updatePipelineWorkflow(pipelineId, stepActive) {
        const stepsCount = 7;
        for (let s = 1; s <= stepsCount; s++) {
            const stepEl = document.getElementById(`${pipelineId}-step-${s}`);
            const connEl = document.getElementById(`${pipelineId}-conn-${s}`);

            if (stepEl) {
                if (s <= stepActive) {
                    stepEl.classList.add('active');
                } else {
                    stepEl.classList.remove('active');
                }
            }
            if (connEl) {
                if (s < stepActive) {
                    connEl.classList.add('active');
                } else {
                    connEl.classList.remove('active');
                }
            }
        }
    }

    // Page 4: Gap Analysis Report
    function renderGapReport(plan) {
        // Fill Metadata
        document.getElementById('lbl-farm-title').innerText = `GAP LAB REPORT: ${plan.farm_id}`;
        document.getElementById('lbl-variety').innerText = plan.variety;
        document.getElementById('lbl-planting').innerText = plan.planting_date;
        document.getElementById('lbl-current-dap').innerText = plan.current_dap + " Days";
        document.getElementById('lbl-last-obs').innerText = plan.last_observation_date || "N/A";
        
        const activeStage = plan.consolidated_intervention_plan[0]?.category || 'GRAND GROWTH';
        document.getElementById('lbl-growth-stage').innerText = activeStage.toUpperCase();

        if (plan.predicted_brix !== undefined) {
            document.getElementById('lbl-predicted-brix').innerText = plan.predicted_brix + "%";
        } else {
            document.getElementById('lbl-predicted-brix').innerText = "N/A";
        }

        // Health Score
        document.getElementById('lbl-health-score').innerText = plan.overall_health_score + "%";

        // Build Heatmap
        const heatmap = document.getElementById('gap-heatmap');
        if (heatmap) {
            heatmap.innerHTML = '';
            for (let idxKey in plan.deviations) {
                const list = plan.deviations[idxKey];
                if (list.length === 0) continue;

                const row = document.createElement('div');
                row.className = 'heatmap-row';
                row.innerHTML = `<span class="heatmap-label">${idxKey}</span>`;

                const cells = document.createElement('div');
                cells.className = 'heatmap-cells';

                list.forEach(b => {
                    const cell = document.createElement('div');
                    cell.className = 'heatmap-cell';

                    // Color according to severity
                    if (b.severity === 'RED') {
                        cell.style.backgroundColor = 'var(--primary-green)';
                    } else if (b.severity === 'YELLOW') {
                        cell.style.backgroundColor = 'var(--light-green)';
                    } else {
                        cell.style.backgroundColor = '#FFFFFF';
                    }
                    cell.title = `DAP ${b.dap_bin}: ${b.severity} (Obs: ${b.observed?.toFixed(2) || 'N/A'}, Ideal: ${b.ideal_mean?.toFixed(2) || 'N/A'})`;
                    cells.appendChild(cell);
                });
                row.appendChild(cells);
                heatmap.appendChild(row);
            }
        }

        // Fill Table rows
        const tblBody = document.getElementById('tbl-deviations-body');
        if (tblBody) {
            tblBody.innerHTML = '';
            for (let idxKey in plan.deviations) {
                const list = plan.deviations[idxKey];
                if (list.length === 0) continue;

                const rowData = list[list.length - 1]; // Latest evaluated bin
                const tr = document.createElement('tr');

                const obs = rowData.observed !== null ? rowData.observed.toFixed(3) : "GAP";
                const ideal = rowData.ideal_mean !== null ? rowData.ideal_mean.toFixed(3) : "N/A";
                const absD = rowData.absolute_deviation !== null ? (rowData.absolute_deviation > 0 ? "+" : "") + rowData.absolute_deviation.toFixed(3) : "--";
                const pctD = rowData.percentage_deviation !== null ? (rowData.percentage_deviation > 0 ? "+" : "") + rowData.percentage_deviation.toFixed(1) + "%" : "--";

                const sevClass = rowData.severity.toLowerCase();
                const checkIcon = '';

                tr.innerHTML = `
                <td style="font-weight:700; color:var(--dark-green);">${idxKey}</td>
                <td>${rowData.growth_stage}</td>
                <td>DAP ${rowData.dap_bin}</td>
                <td>${obs}</td>
                <td>${ideal}</td>
                <td style="font-family:var(--font-mono); font-size:12px;">${absD}</td>
                <td style="font-family:var(--font-mono); font-size:12px;">${pctD}</td>
                <td><span class="severity-pill ${sevClass}">${checkIcon}${rowData.severity}</span></td>
            `;
                tblBody.appendChild(tr);
            }
        }
    }

    // Page 5: Conclusion
    function renderConclusion(plan) {
        // Summary
        document.getElementById('conclusion-farm-id').innerText = plan.farm_id;
        document.getElementById('conclusion-health').innerText = plan.overall_health_score + "%";

        const risk = plan.overall_health_score < 40 ? 'CRITICAL RISK' : (plan.overall_health_score < 75 ? 'MODERATE WATCH' : 'LOW RISK');
        document.getElementById('conclusion-risk').innerText = risk;

        const recovery = 100 - plan.overall_health_score;
        document.getElementById('conclusion-recovery').innerText = "+" + recovery + "% Potential";

        // Cards List
        const container = document.getElementById('conclusion-interventions');
        if (container) {
            container.innerHTML = '';
            plan.consolidated_intervention_plan.forEach(item => {
                const card = document.createElement('div');
                card.className = 'intervention-card';

                const sourceTag = item.source === 'both' ? 'AI & EXPERT RULES' : (item.source === 'rule' ? 'EXPERT RULE ALERT' : 'AGRONOMIST INSIGHT');

                card.innerHTML = `
                <span class="intervention-rank">Rank ${item.priority_rank}</span>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:5px; margin-bottom:8px;">
                    <span class="badge badge-active" style="font-size:9px; border-color:var(--border);">${sourceTag}</span>
                    <span style="font-size:11px; font-weight:700; color:var(--dark-green); text-transform:uppercase;">${item.urgency.replace('_', ' ')}</span>
                </div>
                <div style="font-weight:600; font-size:14px; margin-bottom:6px; color:var(--text); line-height:1.4;">${item.intervention}</div>
                <div style="font-size:12px; color:var(--muted-text); line-height:1.4; margin-bottom:10px;">
                    <strong>Expected outcome:</strong> ${item.expected_outcome}
                </div>
                <div class="intervention-meta">
                    <span>Timing: <strong>${item.timing}</strong></span>
                    <span>Category: <strong>${item.category.toUpperCase()}</strong></span>
                </div>
            `;
                container.appendChild(card);
            });
        }
        
        // Update Yield Projections & Loss Calculator
        const yieldCalcContent = document.getElementById('yield-calculator-content');
        if (yieldCalcContent) {
            const h = plan.overall_health_score !== undefined ? parseFloat(plan.overall_health_score) : 100.0;
            const area = plan.field_area_acres ? parseFloat(plan.field_area_acres) : 1.0;
            
            let idealYieldPerAcre = 50.0; // Default fallback
            if (plan.agronomic_metadata && plan.agronomic_metadata.mean_yield_per_acre) {
                idealYieldPerAcre = parseFloat(plan.agronomic_metadata.mean_yield_per_acre);
            }
            
            if (h >= 95) {
                yieldCalcContent.innerHTML = `
                    <div style="background:rgba(16,185,129,0.04); border:1px solid rgba(16,185,129,0.2); padding:14px; border-radius:8px; display:flex; flex-direction:column; gap:8px;">
                        <div style="font-weight:700; color:var(--dark-green); display:flex; align-items:center; gap:6px; font-size:14px;">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="stroke:var(--dark-green);"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
                            Optimal Crop Performance
                        </div>
                        <div style="font-size:13px; color:var(--text); line-height:1.5;">
                            The crop is performing at <strong>${h.toFixed(1)}%</strong> of its ideal twin benchmark potential. No yield penalties are projected.
                        </div>
                        <div style="margin-top:4px; font-size:12px; font-family:var(--font-mono); color:var(--muted-text); background:rgba(0,0,0,0.03); padding:6px 10px; border-radius:4px; align-self:flex-start; border:1px solid var(--border);">
                            Ideal Yield: ${idealYieldPerAcre.toFixed(1)} tons / acre
                        </div>
                    </div>
                `;
            } else {
                const idealTotal = idealYieldPerAcre * area;
                
                const noActionPerAcre = idealYieldPerAcre * (h / 100.0);
                const noActionTotal = noActionPerAcre * area;
                
                // Recovery is 75% of the gap
                const actionPerAcre = idealYieldPerAcre * ((h + 0.75 * (100.0 - h)) / 100.0);
                const actionTotal = actionPerAcre * area;
                
                const savedPerAcre = actionPerAcre - noActionPerAcre;
                const savedTotal = actionTotal - noActionTotal;
                
                yieldCalcContent.innerHTML = `
                    <div style="display:flex; flex-direction:column; gap:12px; font-size:13px;">
                        <!-- Comparison Cards -->
                        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;">
                            <!-- No Action Card -->
                            <div style="border:1px solid rgba(220,38,38,0.15); background:rgba(220,38,38,0.02); padding:12px; border-radius:8px; display:flex; flex-direction:column; gap:4px;">
                                <div style="font-size:10px; font-weight:700; color:var(--critical-red); text-transform:uppercase; letter-spacing:0.5px;">Ignored Advice</div>
                                <div style="font-size:18px; font-weight:800; color:var(--critical-red); font-family:var(--font-mono);">${noActionPerAcre.toFixed(1)} <span style="font-size:12px; font-weight:600;">t/ac</span></div>
                                <div style="font-size:11px; color:var(--muted-text); font-family:var(--font-mono);">${noActionTotal.toFixed(1)} t total (${area.toFixed(1)} ac)</div>
                            </div>
                            
                            <!-- Follow Recommendations Card -->
                            <div style="border:1px solid rgba(16,185,129,0.25); background:rgba(16,185,129,0.02); padding:12px; border-radius:8px; display:flex; flex-direction:column; gap:4px;">
                                <div style="font-size:10px; font-weight:700; color:var(--dark-green); text-transform:uppercase; letter-spacing:0.5px;">Followed Advice</div>
                                <div style="font-size:18px; font-weight:800; color:var(--dark-green); font-family:var(--font-mono);">${actionPerAcre.toFixed(1)} <span style="font-size:12px; font-weight:600;">t/ac</span></div>
                                <div style="font-size:11px; color:var(--muted-text); font-family:var(--font-mono);">${actionTotal.toFixed(1)} t total (${area.toFixed(1)} ac)</div>
                            </div>
                        </div>

                        <!-- Summary Benefit Alert -->
                        <div style="border:1px solid rgba(245,158,11,0.25); background:rgba(245,158,11,0.03); padding:12px; border-radius:8px; display:flex; flex-direction:column; gap:6px;">
                            <div style="font-weight:700; color:#D97706; display:flex; align-items:center; gap:6px; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="stroke:#D97706;"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                                Net Yield Loss Avoided
                            </div>
                            <div style="font-size:13px; line-height:1.4; color:var(--text);">
                                By executing recommendations, you save <strong style="color:#D97706; font-family:var(--font-mono); font-size:14px;">${savedPerAcre.toFixed(1)} tons / acre</strong>, preventing a loss of <strong style="color:#D97706; font-family:var(--font-mono); font-size:14px;">${savedTotal.toFixed(1)} tons</strong> across your field.
                            </div>
                        </div>

                        <!-- Technical Reference -->
                        <div style="font-size:11px; color:var(--muted-text); line-height:1.4; border-top:1px solid var(--border); padding-top:10px; display:flex; justify-content:space-between;">
                            <span>Variety Baseline: <strong>${idealYieldPerAcre.toFixed(1)} t/ac</strong></span>
                            <span>Target Recovery: <strong>75%</strong></span>
                        </div>
                    </div>
                `;
            }        // Update Impact Simulator
        const simSteps = [
            document.getElementById('sim-step-1'),
            document.getElementById('sim-step-2'),
            document.getElementById('sim-step-3')
        ];
        if (simSteps[0] && simSteps[1] && simSteps[2]) {
            const val1 = plan.overall_health_score;
            const val2 = Math.min(95, Math.round(val1 + (100 - val1) * 0.4));
            const val3 = Math.min(98, Math.round(val2 + (100 - val2) * 0.6));

            simSteps[0].innerHTML = `<div class="simulator-box">${val1}%</div><div style="font-size:10px; color:var(--muted-text); font-weight:600;">Current</div>`;
            simSteps[1].innerHTML = `<div class="simulator-box">${val2}%</div><div style="font-size:10px; color:var(--muted-text); font-weight:600;">Stage 1 Actions</div>`;
            simSteps[2].innerHTML = `<div class="simulator-box">${val3}%</div><div style="font-size:10px; color:var(--muted-text); font-weight:600;">Target Twins</div>`;
        }
    }
}

// --- Leaflet.js Mapping Helpers ---
function addTileLayers(mapObj) {
    const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '© OpenStreetMap contributors'
    });
    
    const esriSatellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 19,
        attribution: 'Tiles &copy; Esri'
    });

    const googleHybrid = L.tileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', {
        maxZoom: 19,
        attribution: 'Map data &copy; Google'
    });
    
    const baseMaps = {
        "Google Satellite (Hybrid)": googleHybrid,
        "Esri Satellite": esriSatellite,
        "Street Map (OSM)": osm
    };
    
    googleHybrid.addTo(mapObj);
    L.control.layers(baseMaps).addTo(mapObj);
}

function initPullMap() {
    if (pullMap) return;
    const mapDiv = document.getElementById('pull-map');
    if (!mapDiv) return;
    
    pullMap = L.map('pull-map').setView([20.78991, 74.13846], 15);
    addTileLayers(pullMap);
    
    pullMarker = L.marker([20.78991, 74.13846], { draggable: true }).addTo(pullMap);
    
    function updateCoords(lat, lng) {
        const latInput = document.getElementById('pull-lat');
        const lonInput = document.getElementById('pull-lon');
        if (latInput) latInput.value = parseFloat(lat).toFixed(5);
        if (lonInput) lonInput.value = parseFloat(lng).toFixed(5);
        updatePullMapCircle();
    }
    
    pullMarker.on('dragend', function (e) {
        const position = pullMarker.getLatLng();
        updateCoords(position.lat, position.lng);
    });
    
    pullMap.on('click', function (e) {
        addPullVertex(e.latlng.lat, e.latlng.lng);
    });
}

function updateCentroidFromPullVertices() {
    if (pullVertices.length === 0) return;
    let sumLat = 0;
    let sumLng = 0;
    for (let i = 0; i < pullVertices.length; i++) {
        sumLat += pullVertices[i][0];
        sumLng += pullVertices[i][1];
    }
    const avgLat = sumLat / pullVertices.length;
    const avgLng = sumLng / pullVertices.length;
    
    const latInput = document.getElementById('pull-lat');
    const lonInput = document.getElementById('pull-lon');
    if (latInput) latInput.value = parseFloat(avgLat).toFixed(5);
    if (lonInput) lonInput.value = parseFloat(avgLng).toFixed(5);
}

function addPullVertex(lat, lng) {
    if (pullMarker) {
        pullMap.removeLayer(pullMarker);
        pullMarker = null;
    }
    
    window.currentPullBoundary = null;
    pullVertices.push([lat, lng]);
    
    const marker = L.circleMarker([lat, lng], {
        radius: 5,
        color: '#2e7d32',
        fillColor: '#81c784',
        fillOpacity: 1
    }).addTo(pullMap);
    pullPointMarkers.push(marker);
    
    if (pullPolygon) {
        pullMap.removeLayer(pullPolygon);
    }
    if (pullCircle) {
        pullMap.removeLayer(pullCircle);
        pullCircle = null;
    }
    
    if (pullVertices.length >= 3) {
        pullPolygon = L.polygon(pullVertices, {
            color: '#2e7d32',
            fillColor: '#81c784',
            fillOpacity: 0.3
        }).addTo(pullMap);
    } else if (pullVertices.length === 2) {
        pullPolygon = L.polyline(pullVertices, {
            color: '#2e7d32'
        }).addTo(pullMap);
    }
    
    updateCentroidFromPullVertices();
}

function clearPullMap() {
    pullPointMarkers.forEach(marker => {
        if (pullMap && marker) {
            pullMap.removeLayer(marker);
        }
    });
    pullPointMarkers = [];
    
    if (pullPolygon && pullMap) {
        pullMap.removeLayer(pullPolygon);
    }
    pullPolygon = null;
    
    if (pullCircle && pullMap) {
        pullMap.removeLayer(pullCircle);
    }
    pullCircle = null;
    
    pullVertices = [];
    window.currentPullBoundary = null;
    
    if (!pullMarker && pullMap) {
        const center = pullMap.getCenter();
        pullMarker = L.marker(center, { draggable: true }).addTo(pullMap);
        
        const latInput = document.getElementById('pull-lat');
        const lonInput = document.getElementById('pull-lon');
        if (latInput) latInput.value = parseFloat(center.lat).toFixed(5);
        if (lonInput) lonInput.value = parseFloat(center.lng).toFixed(5);
        
        pullMarker.on('dragend', function (e) {
            const position = pullMarker.getLatLng();
            const latInput2 = document.getElementById('pull-lat');
            const lonInput2 = document.getElementById('pull-lon');
            if (latInput2) latInput2.value = parseFloat(position.lat).toFixed(5);
            if (lonInput2) lonInput2.value = parseFloat(position.lng).toFixed(5);
            updatePullMapCircle();
        });
        
        updatePullMapCircle();
    }
}

window.clearPullMap = clearPullMap;

function initRawMap() {
    if (rawMap) return;
    const mapDiv = document.getElementById('raw-map');
    if (!mapDiv) return;
    
    rawMap = L.map('raw-map').setView([20.78991, 74.13846], 15);
    addTileLayers(rawMap);
    
    rawMarker = L.marker([20.78991, 74.13846], { draggable: true }).addTo(rawMap);
    
    function updateCoords(lat, lng) {
        const latInput = document.getElementById('raw-lat');
        const lonInput = document.getElementById('raw-lon');
        if (latInput) latInput.value = parseFloat(lat).toFixed(5);
        if (lonInput) lonInput.value = parseFloat(lng).toFixed(5);
    }
    
    rawMarker.on('dragend', function (e) {
        const position = rawMarker.getLatLng();
        updateCoords(position.lat, position.lng);
    });
    
    rawMap.on('click', function (e) {
        addRawVertex(e.latlng.lat, e.latlng.lng);
    });
}

function updateCentroidFromVertices() {
    if (rawVertices.length === 0) return;
    let sumLat = 0;
    let sumLng = 0;
    for (let i = 0; i < rawVertices.length; i++) {
        sumLat += rawVertices[i][0];
        sumLng += rawVertices[i][1];
    }
    const avgLat = sumLat / rawVertices.length;
    const avgLng = sumLng / rawVertices.length;
    
    const latInput = document.getElementById('raw-lat');
    const lonInput = document.getElementById('raw-lon');
    if (latInput) latInput.value = parseFloat(avgLat).toFixed(5);
    if (lonInput) lonInput.value = parseFloat(avgLng).toFixed(5);
}

function addRawVertex(lat, lng) {
    if (rawMarker) {
        rawMap.removeLayer(rawMarker);
        rawMarker = null;
    }
    
    rawVertices.push([lat, lng]);
    
    const marker = L.circleMarker([lat, lng], {
        radius: 5,
        color: '#2e7d32',
        fillColor: '#81c784',
        fillOpacity: 1
    }).addTo(rawMap);
    rawPointMarkers.push(marker);
    
    if (rawPolygon) {
        rawMap.removeLayer(rawPolygon);
    }
    if (rawVertices.length >= 3) {
        rawPolygon = L.polygon(rawVertices, {
            color: '#2e7d32',
            fillColor: '#81c784',
            fillOpacity: 0.3
        }).addTo(rawMap);
    } else if (rawVertices.length === 2) {
        rawPolygon = L.polyline(rawVertices, {
            color: '#2e7d32'
        }).addTo(rawMap);
    }
    
    updateCentroidFromVertices();
}

function clearRawMap() {
    rawPointMarkers.forEach(marker => {
        if (rawMap && marker) {
            rawMap.removeLayer(marker);
        }
    });
    rawPointMarkers = [];
    
    if (rawPolygon && rawMap) {
        rawMap.removeLayer(rawPolygon);
    }
    rawPolygon = null;
    
    rawVertices = [];
    
    if (!rawMarker && rawMap) {
        const center = rawMap.getCenter();
        rawMarker = L.marker(center, { draggable: true }).addTo(rawMap);
        
        const latInput = document.getElementById('raw-lat');
        const lonInput = document.getElementById('raw-lon');
        if (latInput) latInput.value = parseFloat(center.lat).toFixed(5);
        if (lonInput) lonInput.value = parseFloat(center.lng).toFixed(5);
        
        rawMarker.on('dragend', function (e) {
            const position = rawMarker.getLatLng();
            const latInput2 = document.getElementById('raw-lat');
            const lonInput2 = document.getElementById('raw-lon');
            if (latInput2) latInput2.value = parseFloat(position.lat).toFixed(5);
            if (lonInput2) lonInput2.value = parseFloat(position.lng).toFixed(5);
        });
    }
}

window.clearRawMap = clearRawMap;

function updatePullMapCircle() {
    if (!pullMap) return;
    
    const latVal = document.getElementById('pull-lat').value;
    const lonVal = document.getElementById('pull-lon').value;
    const acresVal = document.getElementById('pull-acres').value;
    
    const lat = parseFloat(latVal);
    const lon = parseFloat(lonVal);
    const acres = parseFloat(acresVal) || 1.0;
    
    if (isNaN(lat) || isNaN(lon)) return;
    
    pullMap.setView([lat, lon], 15);
    
    if (pullMarker) {
        pullMarker.setLatLng([lat, lon]);
    }
    
    if (pullCircle) {
        pullMap.removeLayer(pullCircle);
        pullCircle = null;
    }
    if (pullPolygon) {
        pullMap.removeLayer(pullPolygon);
        pullPolygon = null;
    }
    
    if (pullVertices.length >= 3) {
        pullPolygon = L.polygon(pullVertices, {
            color: '#2e7d32',
            fillColor: '#81c784',
            fillOpacity: 0.3
        }).addTo(pullMap);
    } else if (window.currentPullBoundary && window.currentPullBoundary.length >= 3) {
        const latLngs = window.currentPullBoundary.map(pt => [pt.lat, pt.lng]);
        pullPolygon = L.polygon(latLngs, {
            color: '#2e7d32',
            fillColor: '#81c784',
            fillOpacity: 0.3
        }).addTo(pullMap);
    } else {
        const area_sq_m = acres * 4046.85642;
        const radius = Math.sqrt(area_sq_m / Math.PI);
        pullCircle = L.circle([lat, lon], {
            color: '#2e7d32',
            fillColor: '#81c784',
            fillOpacity: 0.3,
            radius: radius
        }).addTo(pullMap);
    }
}

// Function to export and download the last analyzed farm's JSON payload as a file
function exportJsonPayload() {
    if (!lastAnalyzedPlan) {
        alert("No farm analysis has been executed yet. Run an analysis first to export the payload.");
        return;
    }
    
    try {
        const jsonStr = JSON.stringify(lastAnalyzedPlan, null, 2);
        const blob = new Blob([jsonStr], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = `farm_${lastAnalyzedPlan.farm_id}_analysis_payload.json`;
        document.body.appendChild(a);
        a.click();
        
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (err) {
        alert("Failed to export JSON payload. Details: " + err.toString());
    }
}
