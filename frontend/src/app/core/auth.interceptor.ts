import { HttpInterceptorFn } from '@angular/common/http';
import { environment } from '../../environments/environment';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const apiKey = String(environment.apiKey || '').trim();
  if (!apiKey) return next(req);
  return next(req.clone({ setHeaders: { 'X-API-Key': apiKey } }));
};
