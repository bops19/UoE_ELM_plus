import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { SHELL_PAGE_VM } from '../../shell-page.types';
import { ShellVisualTabComponent } from './visual-tab.component';

function signalStub<T>(value: T): () => T {
  return () => value;
}

describe('ShellVisualTabComponent', () => {
  it('creates and can open create-project action via component method', async () => {
    const vm = {
      isImageMediaMode: signalStub(false),
      isVisualMediaTab: signalStub(false),
      isVideoMediaMode: signalStub(false),
      openCreateProjectDialog: vi.fn(),
      assignProjectToSelectedWorkspaceImage: vi.fn(),
    };

    await TestBed.configureTestingModule({
      imports: [ShellVisualTabComponent],
      providers: [{ provide: SHELL_PAGE_VM, useValue: vm }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ShellVisualTabComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.projectMenuOpen = true;
    component.projectPickerOpen = true;

    component.addToNewProject();

    expect(component).toBeTruthy();
    expect(vm.openCreateProjectDialog).toHaveBeenCalled();
    expect(component.projectMenuOpen).toBe(false);
    expect(component.projectPickerOpen).toBe(false);
  });
});
