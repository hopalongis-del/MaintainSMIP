// 2026 SMI event schedule — sourced from Logistics Guru Knowledge_Base/2026_Schedule.md
(function () {
  const SMI_EVENTS_2026 = [
    { name: 'Roar Daytona', dateRange: '1/16-1/18' },
    { name: 'Rolex 24 Daytona', dateRange: '1/22-1/25' },
    { name: 'Bowman Gray', dateRange: '1/31-2/1' },
    { name: 'Daytona', dateRange: '2/12-2/15' },
    { name: 'Atlanta', dateRange: '2/21-2/22' },
    { name: 'Bike Week Daytona', dateRange: '2/27-3/8' },
    { name: 'COTA', dateRange: '2/28-3/1' },
    { name: 'Phoenix', dateRange: '3/7-3/8' },
    { name: 'Vegas', dateRange: '3/14-3/15' },
    { name: 'Darlington', dateRange: '3/20-3/22' },
    { name: 'Martinsville', dateRange: '3/28-3/29' },
    { name: 'Rockingham', dateRange: '4/3-4/4' },
    { name: 'Bristol', dateRange: '4/10-4/12' },
    { name: 'Autofair Charlotte', dateRange: '4/9-4/11' },
    { name: 'Atlanta MJ', dateRange: '4/11-4/12' },
    { name: 'Kansas', dateRange: '4/18-4/19' },
    { name: 'Atlanta Truck Invasion', dateRange: '4/25' },
    { name: 'NHRA Charlotte', dateRange: '4/24-4/26' },
    { name: 'Dega', dateRange: '4/25-4/26' },
    { name: 'Texas', dateRange: '5/1-5/3' },
    { name: 'Rockville Daytona', dateRange: '5/7-5/10' },
    { name: 'Watkins Glen', dateRange: '5/8-5/10' },
    { name: 'Dover Allstar', dateRange: '5/15-5/17' },
    { name: 'Charlotte', dateRange: '5/22-5/24' },
    { name: 'Nashville', dateRange: '5/29-5/31' },
    { name: 'Michigan', dateRange: '6/6-6/7' },
    { name: 'Bonnaroo', dateRange: '6/11-6/14' },
    { name: 'NHRA Bristol', dateRange: '6/12-6/14' },
    { name: 'Pocono', dateRange: '6/13-6/14' },
    { name: 'San Diego', dateRange: '6/19-6/21' },
    { name: 'IMSA Watkins Glen', dateRange: '6/25-6/28' },
    { name: 'Sonoma', dateRange: '6/26-6/28' },
    { name: 'Atlanta Fireworks', dateRange: '7/2' },
    { name: 'Chicagoland', dateRange: '7/4-7/5' },
    { name: 'Atlanta', dateRange: '7/11-7/12' },
    { name: 'NHRA Sonoma', dateRange: '7/17-7/19' },
    { name: 'North Wilkesboro', dateRange: '7/18-7/19' },
    { name: 'Indycar Nashville', dateRange: '7/17-7/19' },
    { name: 'Indianapolis', dateRange: '7/25-7/26' },
    { name: 'Lollapalooza', dateRange: '7/30-8/2' },
    { name: 'Iowa', dateRange: '8/8-8/9' },
    { name: 'Richmond', dateRange: '8/14-8/15' },
    { name: 'NHMS', dateRange: '8/22-8/23' },
    { name: 'Daytona', dateRange: '8/28-8/29' },
    { name: 'Darlington', dateRange: '9/5-9/6' },
    { name: 'WWTR St. Louis', dateRange: '9/12-9/13' },
    { name: 'Bristol Rhytm Roots', dateRange: '9/11-9/13' },
    { name: 'Bristol', dateRange: '9/17-9/19' },
    { name: 'Charlotte Breakaway', dateRange: '9/25-9/26' },
    { name: 'Kansas', dateRange: '9/26-9/27' },
    { name: 'LVMS', dateRange: '10/3-10/4' },
    { name: 'Charlotte', dateRange: '10/9-10/11' },
    { name: 'Phoenix', dateRange: '10/16-10/18' },
    { name: 'Dega', dateRange: '10/23-10/25' },
    { name: 'COTA F1', dateRange: '10/23-10/25' },
    { name: 'NHRA LVMS', dateRange: '10/29-11/1' },
    { name: 'Martinsville', dateRange: '10/30-11/1' },
    { name: 'WOO Charlotte', dateRange: '11/4-11/7' },
    { name: 'Homestead Miami', dateRange: '11/6-11/8' },
  ];

  function formatEventLabel(event) {
    return `${event.name} (${event.dateRange})`;
  }

  function getEventOptionValue(event) {
    return formatEventLabel(event);
  }

  function getSmiEventOptions() {
    return SMI_EVENTS_2026.map((event) => ({
      value: getEventOptionValue(event),
      label: formatEventLabel(event),
      name: event.name,
      dateRange: event.dateRange,
    }));
  }

  window.MaintainSMIPEvents = {
    SMI_EVENTS_2026,
    formatEventLabel,
    getEventOptionValue,
    getSmiEventOptions,
  };
})();