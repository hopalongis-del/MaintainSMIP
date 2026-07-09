self.addEventListener('push', (event) => {
  let payload = { title: 'Fleet Maintain', body: 'You have a new fleet alert.', url: '/index.html' };
  try {
    if (event.data) {
      payload = { ...payload, ...event.data.json() };
    }
  } catch (err) {
    payload.body = event.data?.text() || payload.body;
  }

  event.waitUntil(
    self.registration.showNotification(payload.title || 'Fleet Maintain', {
      body: payload.body || '',
      icon: '/logo.svg',
      badge: '/logo.svg',
      tag: payload.tag || 'fleet-maintain-alert',
      data: { url: payload.url || '/index.html' },
    }),
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = event.notification.data?.url || '/index.html';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      for (const client of windowClients) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
      return undefined;
    }),
  );
});