(function () {
    const STORAGE_KEY = 'wms_shelf_display_mode';

    function normalizeMode(mode) {
        return mode === 'caixa' ? 'caixa' : 'os';
    }

    function getLabel(block, mode) {
        const orderId = String(block.dataset.orderId || '').trim();
        const boxNumber = String(block.dataset.boxNumber || '').trim();

        if (mode === 'caixa') {
            return boxNumber || orderId || '-';
        }

        return orderId || boxNumber || '-';
    }

    function updateMode(mode) {
        const activeMode = normalizeMode(mode);

        document.querySelectorAll('.box-block[data-order-id], .box-block[data-box-number]').forEach((block) => {
            const label = getLabel(block, activeMode);
            const ageDays = String(block.dataset.ageDays || '').trim();

            block.textContent = label;
            block.title = ageDays ? `${label} (${ageDays}d)` : label;
        });

        document.querySelectorAll('[data-shelf-display-mode]').forEach((button) => {
            const isActive = button.dataset.shelfDisplayMode === activeMode;
            button.classList.toggle('active', isActive);
            button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });

        document.querySelectorAll('[data-shelf-display-mode-label]').forEach((label) => {
            label.textContent = activeMode === 'caixa' ? 'Caixa' : 'OS';
        });
    }

    function setMode(mode, persist) {
        const activeMode = normalizeMode(mode);
        updateMode(activeMode);

        if (persist !== false) {
            localStorage.setItem(STORAGE_KEY, activeMode);
        }
    }

    function init() {
        const savedMode = localStorage.getItem(STORAGE_KEY);
        setMode(savedMode === 'caixa' ? 'caixa' : 'os', false);

        document.addEventListener('click', (event) => {
            const button = event.target.closest('[data-shelf-display-mode]');
            if (!button) {
                return;
            }

            event.preventDefault();
            setMode(button.dataset.shelfDisplayMode || 'os');
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.ShelfDisplayMode = {
        setMode: (mode) => setMode(mode),
        refresh: () => updateMode(normalizeMode(localStorage.getItem(STORAGE_KEY))),
        getMode: () => normalizeMode(localStorage.getItem(STORAGE_KEY)),
    };
})();