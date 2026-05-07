import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges } from '@angular/core';
import { A11yModule } from '@angular/cdk/a11y';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-text-input-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, A11yModule],
  templateUrl: './text-input-dialog.component.html',
  styleUrl: './text-input-dialog.component.css',
})
export class TextInputDialogComponent implements OnChanges {
  @Input() title = '';
  @Input() placeholder = '';
  @Input() confirmLabel = 'OK';
  @Input() initialValue = '';
  @Output() canceled = new EventEmitter<void>();
  @Output() confirmed = new EventEmitter<string>();

  readonly titleId = `text-dialog-${Math.random().toString(36).slice(2, 8)}`;
  value = '';

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['initialValue']) {
      this.value = this.initialValue ?? '';
    }
  }

  confirm(): void {
    const trimmed = this.value.trim();
    if (!trimmed) return;
    this.confirmed.emit(trimmed);
  }

  cancel(): void {
    this.canceled.emit();
  }
}
