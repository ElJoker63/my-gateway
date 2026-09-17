import { createApp } from "vue";
import { route } from "./router.js";
import App from "./App.js";
import OverviewView from "./views/OverviewView.js";
import ProvidersView from "./views/ProvidersView.js";
import KeysView from "./views/KeysView.js";
import CombosView from "./views/CombosView.js";
import MetricsView from "./views/MetricsView.js";
import SettingsView from "./views/SettingsView.js";
import LoginView from "./views/LoginView.js";

const routes = {
  "/": OverviewView,
  "/providers": ProvidersView,
  "/keys": KeysView,
  "/combos": CombosView,
  "/metrics": MetricsView,
  "/settings": SettingsView,
  "/login": LoginView,
};

const app = createApp(App, { routes: {}, initialRoutes: routes });
app.provide("routes", routes);
app.mount("#app");
