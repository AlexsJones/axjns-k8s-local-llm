// Hardware picker: one choice drives every hardware-specific block on the page
// (anything with data-hw="cpu|intel|nvidia|amd"), and it's remembered.
(function () {
  var KEY = "axjns-k8s-local-llm-hw";
  var valid = ["cpu", "intel", "nvidia", "amd"];
  function set(hw) {
    if (valid.indexOf(hw) < 0) hw = "cpu";
    valid.forEach(function (h) { document.body.classList.toggle("hw-" + h, h === hw); });
    document.querySelectorAll(".tabs button").forEach(function (b) {
      b.setAttribute("aria-selected", b.dataset.select === hw ? "true" : "false");
    });
    try { localStorage.setItem(KEY, hw); } catch (e) {}
    if (history.replaceState) history.replaceState(null, "", "#hw=" + hw);
  }
  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-select]");
    if (t) { set(t.dataset.select); return; }
    var c = e.target.closest(".copy");
    if (c) {
      var code = c.parentElement.querySelector("code").innerText;
      navigator.clipboard.writeText(code).then(function () {
        c.textContent = "copied"; setTimeout(function () { c.textContent = "copy"; }, 1200);
      });
    }
  });
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("pre:not(.out)").forEach(function (p) {
      var b = document.createElement("button");
      b.className = "copy"; b.type = "button"; b.textContent = "copy";
      p.appendChild(b);
    });
    var m = location.hash.match(/hw=(\w+)/);
    var saved = null; try { saved = localStorage.getItem(KEY); } catch (e) {}
    set(m ? m[1] : saved || "cpu");
  });
})();
