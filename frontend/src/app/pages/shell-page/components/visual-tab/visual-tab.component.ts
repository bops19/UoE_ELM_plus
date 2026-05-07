import { Component, HostListener, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { SHELL_PAGE_VM } from '../../shell-page.types';
import type { ShellPageVm } from '../../shell-page.types';

@Component({
  selector: 'app-shell-visual-tab',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './visual-tab.component.html',
  styleUrls: ['./visual-tab.component.css'],
})
export class ShellVisualTabComponent {
  readonly vm = inject(SHELL_PAGE_VM) as ShellPageVm;
  projectMenuOpen = false;
  projectPickerOpen = false;

  @HostListener('document:click')
  onDocumentClick(): void {
    this.closeProjectMenu();
  }

  toggleProjectMenu(event?: Event): void {
    if (event) event.stopPropagation();
    this.projectMenuOpen = !this.projectMenuOpen;
    if (!this.projectMenuOpen) this.projectPickerOpen = false;
  }

  toggleProjectPicker(event?: Event): void {
    if (event) event.stopPropagation();
    this.projectPickerOpen = !this.projectPickerOpen;
  }

  closeProjectMenu(event?: Event): void {
    if (event) event.stopPropagation();
    this.projectMenuOpen = false;
    this.projectPickerOpen = false;
  }

  assignToProject(projectId: string, event?: Event): void {
    if (event) event.stopPropagation();
    this.vm.assignProjectToSelectedWorkspaceImage(projectId);
    this.closeProjectMenu();
  }

  addToNewProject(event?: Event): void {
    if (event) event.stopPropagation();
    this.vm.openCreateProjectDialog();
    this.closeProjectMenu();
  }
}
