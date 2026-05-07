import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { SHELL_PAGE_VM } from '../../shell-page.types';
import type { ShellPageVm } from '../../shell-page.types';

@Component({
  selector: 'app-shell-computer-tab',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './computer-tab.component.html',
})
export class ShellComputerTabComponent {
  readonly vm = inject(SHELL_PAGE_VM) as ShellPageVm;
}
