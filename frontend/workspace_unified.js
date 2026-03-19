/**
 * Workspace Unificato - Layout 3 colonne (Eventi | Video | Clip)
 * Espone getVideoSlotRect() per il posizionamento dell'overlay video Qt.
 */
(function() {
    document.addEventListener('DOMContentLoaded', function() {
        var tabs = document.querySelectorAll('.unified-tab');
        var panes = document.querySelectorAll('.unified-pane');
        if (tabs.length && panes.length) {
            tabs.forEach(function(tab) {
                tab.addEventListener('click', function() {
                    var target = tab.dataset.tab;
                    tabs.forEach(function(t) { t.classList.remove('active'); });
                    panes.forEach(function(p) {
                        p.classList.toggle('active', p.id === 'pane-' + target);
                    });
                    tab.classList.add('active');
                });
            });
        }
    });
})();

/** Restituisce { x, y, w, h } dello slot video (coordinate viewport) per overlay Qt. */
function getVideoSlotRect() {
    var el = document.getElementById('video-slot');
    if (!el) return null;
    var r = el.getBoundingClientRect();
    return { x: r.left, y: r.top, w: r.width, h: r.height };
}
