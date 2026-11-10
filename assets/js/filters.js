(function () {
  const statusPills = document.querySelectorAll('[data-filter-status]');
  const blockPills = document.querySelectorAll('[data-filter-block]');
  const originPills = document.querySelectorAll('[data-filter-origin]');
  const cards = document.querySelectorAll('.demo-card');
  const navLinks = document.querySelectorAll('[data-filter-nav]');
  const searchInput = document.getElementById('demo-search');
  const emptyState = document.getElementById('filter-empty');

  if (!cards.length) return;

  let activeStatus = 'all';
  let activeBlock = null;
  let activeOrigin = null;

  function cardMatchesStatus(card, status) {
    if (status === 'all') return true;
    return card.dataset.status === status;
  }

  function cardMatchesBlock(card, block) {
    if (!block) return true;
    const blocks = (card.dataset.buildingBlocks || '').split(',').filter(Boolean);
    return blocks.indexOf(block) >= 0;
  }

  function cardMatchesOrigin(card, origin) {
    if (!origin) return true;
    return card.dataset.origin === origin;
  }

  function cardMatchesSearch(card, query) {
    if (!query) return true;
    const haystack = (card.dataset.search || '').toLowerCase();
    return haystack.indexOf(query) >= 0;
  }

  function setActiveStatusPill(status) {
    statusPills.forEach(function (pill) {
      pill.classList.toggle('active', pill.dataset.filterStatus === status);
    });
  }

  function setActiveBlockPill(block) {
    blockPills.forEach(function (pill) {
      pill.classList.toggle('active', block && pill.dataset.filterBlock === block);
    });
  }

  function setActiveOriginPill(origin) {
    originPills.forEach(function (pill) {
      pill.classList.toggle('active', origin && pill.dataset.filterOrigin === origin);
    });
  }

  function applyFilters() {
    const query = searchInput ? searchInput.value.trim().toLowerCase() : '';
    let visibleCount = 0;

    cards.forEach(function (card) {
      const show =
        cardMatchesStatus(card, activeStatus) &&
        cardMatchesBlock(card, activeBlock) &&
        cardMatchesOrigin(card, activeOrigin) &&
        cardMatchesSearch(card, query);
      card.classList.toggle('hidden', !show);
      if (show) visibleCount += 1;
    });

    document.querySelectorAll('.section').forEach(function (section) {
      const visible = section.querySelectorAll('.demo-card:not(.hidden)').length;
      section.style.display = visible > 0 ? '' : 'none';
    });

    if (emptyState) {
      emptyState.classList.toggle('hidden', visibleCount > 0);
    }
  }

  function applyBlockFilter(block) {
    activeBlock = block;
    setActiveBlockPill(activeBlock);
    applyFilters();
  }

  function applyOriginFilter(origin) {
    activeOrigin = origin;
    setActiveOriginPill(activeOrigin);
    applyFilters();
  }

  function applyStatusFilter(status) {
    activeStatus = status;
    setActiveStatusPill(activeStatus);
    applyFilters();
  }

  function readFiltersFromUrl() {
    var params = new URLSearchParams(window.location.search);
    var originParam = params.get('origin');
    if (originParam === 'tmm-created' || originParam === 'ai-generated') {
      applyOriginFilter(originParam);
    }

    var blockParam = params.get('block');
    if (blockParam) {
      applyBlockFilter(blockParam);
      return;
    }

    var hash = window.location.hash.replace('#', '');
    if (hash === 'active' || hash === 'coming-soon') {
      applyStatusFilter(hash);
      return;
    }

    if (hash.indexOf('block-') === 0) {
      applyBlockFilter(hash.slice(6));
      return;
    }

    if (hash === 'tmm-created' || hash === 'ai-generated') {
      applyOriginFilter(hash);
    }
  }

  statusPills.forEach(function (pill) {
    pill.addEventListener('click', function () {
      applyStatusFilter(pill.dataset.filterStatus);
    });
  });

  blockPills.forEach(function (pill) {
    pill.addEventListener('click', function () {
      const block = pill.dataset.filterBlock;
      applyBlockFilter(activeBlock === block ? null : block);
    });
  });

  originPills.forEach(function (pill) {
    pill.addEventListener('click', function () {
      const origin = pill.dataset.filterOrigin;
      applyOriginFilter(activeOrigin === origin ? null : origin);
    });
  });

  if (searchInput) {
    searchInput.addEventListener('input', applyFilters);
  }

  navLinks.forEach(function (link) {
    link.addEventListener('click', function (e) {
      const filter = link.dataset.filterNav;
      if (filter && statusPills.length) {
        e.preventDefault();
        activeBlock = null;
        activeOrigin = null;
        setActiveBlockPill(null);
        setActiveOriginPill(null);
        applyStatusFilter(filter);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    });
  });

  readFiltersFromUrl();
  applyFilters();
})();
