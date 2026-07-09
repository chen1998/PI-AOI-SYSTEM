
// static/js/ol_defect_map/router.js
(function () {
  const Router = {
    _inited: false,

    async ensureInit() {
      if (this._inited) {
        //console.log("[OL_DEFECT_MAP_Router] already inited");
        return;
      }
      this._inited = true;

      //console.log("[OL_DEFECT_MAP_Router] ensureInit start");

      const root = document.getElementById("ol-defect-map-root");
      if (!root) {
        console.warn("[OL_DEFECT_MAP_Router] root not found");
        return;
      }

      /*console.log("[OL_DEFECT_MAP_Router] dependencies", {
        hasAPIController: !!window.OLDefectMapAPIController,
        hasBus: !!window.OLDefectMapBus,
        hasState: !!window.OLDefectMapState,
      });*/

      if (typeof window.OLDefectMapAPIController?.init === "function") {
        await window.OLDefectMapAPIController.init();
        //console.log("[OL_DEFECT_MAP_Router] API init done");
      } else {
        console.warn("[OL_DEFECT_MAP_Router] OLDefectMapAPIController.init not found");
      }
    }
  };

  window.OL_DEFECT_MAP_Router = Router;
})();
