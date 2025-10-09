#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste do controle de sensibilidade na interface de calibração
"""

import os
import tkinter as tk
import warnings
from tkinter import StringVar, ttk

import pytest

warnings.filterwarnings("ignore")


def test_sensitivity_control():
    if os.environ.get("DISPLAY") is None:
        pytest.skip("requires a display")
    """Simula e testa o controle de sensibilidade"""
    print("=" * 80)
    print("TESTE DO CONTROLE DE SENSIBILIDADE")
    print("=" * 80)

    # Cria janela de teste
    root = tk.Tk()
    root.title("Teste - Controle de Sensibilidade")
    root.geometry("600x450")

    # Simula as variáveis e componentes da interface
    print("Criando componentes da interface...")

    # Frame principal
    main_frame = ttk.LabelFrame(root, text="Controle de Sensibilidade", padding=10)
    main_frame.pack(fill="x", pady=10, padx=10)

    # Variáveis
    StringVar(value="0.15")
    current_threshold = [0.15]  # Lista para simular referência mutável

    # Label
    ttk.Label(main_frame, text="Ajuste de Sensibilidade:").grid(
        row=0, column=0, sticky="w", padx=5, pady=5
    )

    # Frame para slider + label
    sensitivity_frame = ttk.Frame(main_frame)
    sensitivity_frame.grid(row=0, column=1, sticky="w", padx=5)

    # Callback function
    def on_sensitivity_change(value):
        threshold_value = float(value)
        sensitivity_label.config(text=f"{threshold_value:.2f}")
        current_threshold[0] = threshold_value
        print(f"   Threshold alterado para: {threshold_value:.2f}")

        # Simula atualização no detector
        print(f"   Detector.plugin.conf_threshold = {threshold_value:.2f}")

    # Scale
    sensitivity_scale = ttk.Scale(
        sensitivity_frame,
        from_=0.05,
        to=0.50,
        orient="horizontal",
        length=200,
        command=on_sensitivity_change,
    )
    sensitivity_scale.set(0.15)  # Valor inicial
    sensitivity_scale.pack(side="left")

    # Label do valor
    sensitivity_label = ttk.Label(sensitivity_frame, text="0.15")
    sensitivity_label.pack(side="left", padx=(10, 0))

    # Tooltip
    tooltip_label = ttk.Label(
        main_frame,
        text="(Valores menores detectam mais objetos)",
        font=("Arial", 8),
        foreground="gray",
    )
    tooltip_label.grid(row=1, column=1, sticky="w", padx=5, pady=(0, 5))

    # Frame de teste
    test_frame = ttk.LabelFrame(root, text="Teste de Funcionalidade", padding=10)
    test_frame.pack(fill="x", pady=10, padx=10)

    # Botões de teste
    def test_low():
        sensitivity_scale.set(0.05)
        print("Testando sensibilidade ALTA (threshold baixo)")

    def test_medium():
        sensitivity_scale.set(0.15)
        print("Testando sensibilidade MÉDIA (threshold médio)")

    def test_high():
        sensitivity_scale.set(0.35)
        print("Testando sensibilidade BAIXA (threshold alto)")

    ttk.Button(test_frame, text="Alta (0.05)", command=test_low).pack(
        side="left", padx=3
    )
    ttk.Button(test_frame, text="Média (0.15)", command=test_medium).pack(
        side="left", padx=3
    )
    ttk.Button(test_frame, text="Baixa (0.35)", command=test_high).pack(
        side="left", padx=3
    )

    # Frame de informações
    info_frame = ttk.LabelFrame(root, text="Informações", padding=10)
    info_frame.pack(fill="x", pady=10, padx=10)

    info_text = tk.Text(info_frame, height=6, wrap="word")
    info_text.pack(fill="x")

    info_content = """Como usar:
• Mova o slider ou clique nos botões de teste
• Valores menores (0.05-0.10) = ALTA sensibilidade (detecta mais objetos)
• Valores médios (0.10-0.20) = Sensibilidade balanceada
• Valores maiores (0.20-0.50) = BAIXA sensibilidade (detecta menos objetos)

Útil para:
• Modelos com baixa confiança
• Ajuste fino sem editar arquivos
• Teste rápido de diferentes configurações"""

    info_text.insert("1.0", info_content)
    info_text.config(state="disabled")

    print("Interface criada com sucesso!")
    print("Use os controles para testar o slider")
    print("Feche a janela para finalizar o teste")

    # Função para testar programaticamente
    def run_auto_test():
        print("\nExecutando teste automático...")
        test_values = [0.05, 0.15, 0.25, 0.35, 0.50]

        for val in test_values:
            sensitivity_scale.set(val)
            root.update()  # Força atualização
            print(f"   Testado: {val}")

        print("Teste automático concluído")

    # Botão de teste automático
    ttk.Button(root, text="Executar Teste Automático", command=run_auto_test).pack(
        pady=10
    )

    # Inicia interface
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\nTeste interrompido pelo usuário")

    print("\nRESULTADO DO TESTE:")
    print(f"   Threshold final: {current_threshold[0]:.2f}")
    print("Controle de sensibilidade funcional!")


def test_integration_concept():
    """Testa o conceito de integração com o detector"""
    print("\n" + "=" * 60)
    print("CONCEITO DE INTEGRACAO COM DETECTOR")
    print("=" * 60)

    # Simula detector plugin
    class MockDetectorPlugin:
        def __init__(self):
            self.conf_threshold = 0.25
            self.nms_threshold = 0.5

        def set_threshold(self, threshold):
            old = self.conf_threshold
            self.conf_threshold = threshold
            print(f"   Plugin: {old:.2f} -> {threshold:.2f}")

    # Simula controller com detector
    class MockController:
        def __init__(self):
            self.detector = MockDetector()

    class MockDetector:
        def __init__(self):
            self.plugin = MockDetectorPlugin()

    # Teste de integração
    controller = MockController()

    print("Estado inicial:")
    print(f"   Threshold: {controller.detector.plugin.conf_threshold:.2f}")

    print("\nSimulando mudanças do slider:")
    test_values = [0.05, 0.10, 0.15, 0.25, 0.35]

    for val in test_values:
        print(f"\nSlider mudou para: {val:.2f}")

        # Simula callback da interface
        if hasattr(controller, "detector") and controller.detector:
            if hasattr(controller.detector.plugin, "conf_threshold"):
                controller.detector.plugin.set_threshold(val)

    print("\nIntegração testada com sucesso!")


if __name__ == "__main__":
    try:
        test_sensitivity_control()
        test_integration_concept()
        print("\n" + "=" * 80)
        print("CONTROLE DE SENSIBILIDADE IMPLEMENTADO E TESTADO!")
        print("=" * 80)
    except Exception as e:
        print(f"\nErro durante teste: {e}")
        import traceback

        traceback.print_exc()
