/* global L */

const API_URL = "/api/v1/routes/plan/";

const form = document.getElementById("planner-form");
const startInput = document.getElementById("start-input");
const finishInput = document.getElementById("finish-input");
const submitBtn = document.getElementById("submit-btn");
const btnLabel = submitBtn.querySelector(".btn-label");
const btnSpinner = submitBtn.querySelector(".btn-spinner");
const errorBanner = document.getElementById("error-banner");
const resultsPanel = document.getElementById("results-panel");
const mapOverlay = document.getElementById("map-overlay");
const fuelStopList = document.getElementById("fuel-stop-list");
const noStopsMessage = document.getElementById("no-stops-message");
const fuelStopCount = document.getElementById("fuel-stop-count");

const statDistance = document.getElementById("stat-distance");
const statDuration = document.getElementById("stat-duration");
const statCost = document.getElementById("stat-cost");
const statGallons = document.getElementById("stat-gallons");

let map;
let routeLayer;
let markersLayer;

function initMap() {
  map = L.map("map", { zoomControl: true }).setView([39.8283, -98.5795], 4);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19,
  }).addTo(map);

  routeLayer = L.geoJSON(null, {
    style: {
      color: "#38bdf8",
      weight: 5,
      opacity: 0.92,
      lineCap: "round",
      lineJoin: "round",
    },
  }).addTo(map);

  markersLayer = L.layerGroup().addTo(map);
}

function setLoading(isLoading) {
  submitBtn.disabled = isLoading;
  btnSpinner.hidden = !isLoading;
  btnLabel.textContent = isLoading ? "Planning..." : "Plan Route";
}

function showError(message) {
  errorBanner.hidden = false;
  errorBanner.textContent = message;
}

function clearError() {
  errorBanner.hidden = true;
  errorBanner.textContent = "";
}

function formatDuration(seconds) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.round((seconds % 3600) / 60);
  if (hours === 0) {
    return `${minutes} min`;
  }
  return `${hours} hr ${minutes} min`;
}

function formatCurrency(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(value);
}

function createMarkerIcon(kind, label = "") {
  const colors = {
    start: { bg: "#34d399", ring: "rgba(52, 211, 153, 0.25)" },
    finish: { bg: "#f472b6", ring: "rgba(244, 114, 182, 0.25)" },
    fuel: { bg: "#fbbf24", ring: "rgba(251, 191, 36, 0.25)" },
  };
  const palette = colors[kind] || colors.fuel;

  return L.divIcon({
    className: "custom-marker",
    html: `<div style="
      width: ${kind === "fuel" ? "30px" : "18px"};
      height: ${kind === "fuel" ? "30px" : "18px"};
      border-radius: 50%;
      background: ${palette.bg};
      border: 3px solid #0f172a;
      box-shadow: 0 0 0 6px ${palette.ring};
      display: grid;
      place-items: center;
      color: #0f172a;
      font-size: 11px;
      font-weight: 800;
    ">${label}</div>`,
    iconSize: kind === "fuel" ? [30, 30] : [18, 18],
    iconAnchor: kind === "fuel" ? [15, 15] : [9, 9],
  });
}

function popupHtml(title, lines) {
  return `
    <div>
      <p class="popup-title">${title}</p>
      ${lines.map((line) => `<p class="popup-meta">${line}</p>`).join("")}
    </div>
  `;
}

function renderMap(data) {
  markersLayer.clearLayers();
  routeLayer.clearLayers();

  if (data.route) {
    routeLayer.addData(data.route);
  }

  if (data.map?.features) {
    data.map.features.forEach((feature) => {
      const kind = feature.properties?.kind;
      const coords = feature.geometry.coordinates;
      const latLng = [coords[1], coords[0]];

      if (kind === "start") {
        L.marker(latLng, { icon: createMarkerIcon("start") })
          .bindPopup(
            popupHtml(feature.properties.label || "Start", ["Trip starting point"])
          )
          .addTo(markersLayer);
      }

      if (kind === "finish") {
        L.marker(latLng, { icon: createMarkerIcon("finish") })
          .bindPopup(
            popupHtml(feature.properties.label || "Finish", ["Trip destination"])
          )
          .addTo(markersLayer);
      }

      if (kind === "fuel_stop") {
        L.marker(latLng, { icon: createMarkerIcon("fuel", "⛽") })
          .bindPopup(
            popupHtml(feature.properties.name || "Fuel stop", [
              `$${Number(feature.properties.retail_price).toFixed(2)}/gal`,
              `Stop cost: ${formatCurrency(Number(feature.properties.fuel_cost_usd || 0))}`,
            ])
          )
          .addTo(markersLayer);
      }
    });
  }

  const bounds = routeLayer.getBounds();
  if (bounds.isValid()) {
    map.fitBounds(bounds.pad(0.12));
  }

  mapOverlay.classList.add("hidden");
}

function renderFuelStops(stops) {
  fuelStopList.innerHTML = "";
  fuelStopCount.textContent = String(stops.length);
  noStopsMessage.hidden = stops.length > 0;

  stops.forEach((stop, index) => {
    const item = document.createElement("li");
    item.className = "fuel-stop-item";
    item.innerHTML = `
      <header>
        <span class="stop-index">${index + 1}</span>
        <span class="stop-name">${stop.name}</span>
        <span class="stop-price">${formatCurrency(stop.fuel_cost_usd)}</span>
      </header>
      <div class="stop-meta">
        ${stop.city}, ${stop.state} · $${stop.retail_price.toFixed(2)}/gal ·
        ${stop.gallons_purchased.toFixed(1)} gal ·
        mile ${stop.distance_along_route_miles.toFixed(0)}
      </div>
    `;

    item.addEventListener("click", () => {
      document.querySelectorAll(".fuel-stop-item").forEach((el) => {
        el.classList.remove("active");
      });
      item.classList.add("active");

      const [lng, lat] = stop.location.coordinates;
      map.flyTo([lat, lng], 10, { duration: 0.8 });
    });

    fuelStopList.appendChild(item);
  });
}

function renderResults(data) {
  statDistance.textContent = `${data.distance_miles.toFixed(1)} mi`;
  statDuration.textContent = formatDuration(data.duration_seconds);
  statCost.textContent = formatCurrency(data.total_fuel_cost_usd);
  statGallons.textContent = `${data.total_gallons_consumed.toFixed(1)} gal`;

  renderFuelStops(data.fuel_stops || []);
  renderMap(data);
  resultsPanel.hidden = false;
}

async function planRoute(start, finish) {
  const response = await fetch(API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ start, finish }),
  });

  const payload = await response.json();

  if (!response.ok) {
    const message =
      payload?.error?.message ||
      payload?.detail ||
      "Unable to plan route. Please check your locations and try again.";
    throw new Error(message);
  }

  return payload;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();

  const start = startInput.value.trim();
  const finish = finishInput.value.trim();

  if (!start || !finish) {
    showError("Please enter both start and finish locations.");
    return;
  }

  setLoading(true);

  try {
    const data = await planRoute(start, finish);
    renderResults(data);
  } catch (error) {
    showError(error.message || "Something went wrong while planning the route.");
  } finally {
    setLoading(false);
  }
});

document.querySelectorAll(".preset-btn").forEach((button) => {
  button.addEventListener("click", () => {
    startInput.value = button.dataset.start;
    finishInput.value = button.dataset.finish;
    form.requestSubmit();
  });
});

initMap();
