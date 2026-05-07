import { TestBed } from '@angular/core/testing';
import { SHELL_PAGE_VM } from '../../shell-page.types';
import { ShellDeepTabComponent } from './deep-tab.component';

describe('ShellDeepTabComponent', () => {
  it('creates and renders the deep research heading', async () => {
    await TestBed.configureTestingModule({
      imports: [ShellDeepTabComponent],
      providers: [{ provide: SHELL_PAGE_VM, useValue: {} }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ShellDeepTabComponent);
    fixture.detectChanges();

    expect(fixture.componentInstance).toBeTruthy();
    expect(fixture.nativeElement.textContent).toContain('Deep Research');
  });
});
