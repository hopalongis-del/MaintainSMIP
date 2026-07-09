// Optional event schedule for location/event dropdowns (not customer-specific).
(function () {
  const EVENTS_2026 = [
    { name: 'Season Opener', dateRange: '1/16-1/18' },
    { name: 'Spring Event', dateRange: '3/7-3/8' },
    { name: 'Mid-Season', dateRange: '5/22-5/24' },
    { name: 'Summer Event', dateRange: '7/11-7/12' },
    { name: 'Late Season', dateRange: '9/5-9/6' },
    { name: 'Season Finale', dateRange: '11/6-11/8' },
  ];

  function formatEventLabel(event) {
    return `${event.name} (${event.dateRange})`;
  }

  function getEventOptionValue(event) {
    return formatEventLabel(event);
  }

  function getEventOptions() {
    return EVENTS_2026.map((event) => ({
      value: getEventOptionValue(event),
      label: formatEventLabel(event),
      name: event.name,
      dateRange: event.dateRange,
    }));
  }

  // Back-compat aliases for older settings.js callers
  const getSmiEventOptions = getEventOptions;

  window.MaintainSMIPEvents = {
    EVENTS_2026,
    SMI_EVENTS_2026: EVENTS_2026,
    formatEventLabel,
    getEventOptionValue,
    getEventOptions,
    getSmiEventOptions,
  };
})();
