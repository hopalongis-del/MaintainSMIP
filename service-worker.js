self.addEventListener('push', (event) => {
  let payload = { title: 'MaintainSMIP', body: 'You have a new fleet alert.', url: '/index.html' };
  try {
    if (event.data) {
      payload = { ...payload, ...event.data.json() };
    }
  } catch (err) {
    payload.body = event.data?.text() || payload.body;
  }

  event.waitUntil(
    self.registration.showNotification(payload.title || 'MaintainSMIP', {
      body: payload.body || '',
      icon: '/logo1.png',
      badge: '/logo1.png',
      tag: payload.tag || 'maintainsmip-alert',
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