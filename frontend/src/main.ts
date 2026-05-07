import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';
import { environment } from './environments/environment';

async function bootstrap(): Promise<void> {
  const sentryDsn = String(environment.sentryDsn || '').trim();
  if (sentryDsn) {
    const Sentry = await import('@sentry/angular');
    Sentry.init({
      dsn: sentryDsn,
      tracesSampleRate: 0.1,
      environment: environment.name,
    });
  }

  bootstrapApplication(App, appConfig)
    .catch((err) => console.error(err));
}

void bootstrap();
