(function () {
  var el = document.getElementById('legal-map');
  var lm = document.getElementById('new-load-model');
  var mode = document.getElementById('new-mode');
  if (!el || !lm || !mode) return;
  var LEGAL = JSON.parse(el.textContent);
  function sync() {
    var allowed = LEGAL[lm.value] || [];
    mode.innerHTML = '';
    allowed.forEach(function (m) {
      var o = document.createElement('option');
      o.value = m; o.textContent = m;
      mode.appendChild(o);
    });
  }
  lm.addEventListener('change', sync);
  sync();
})();
