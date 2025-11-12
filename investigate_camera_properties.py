"""
Script para investigar propriedades disponíveis das câmeras.
Testa múltiplas propriedades do OpenCV/DirectShow para encontrar diferenciadores.
"""

import sys

import cv2


def get_all_camera_properties(index):
    """Extrai todas as propriedades possíveis de uma câmera."""
    try:
        if sys.platform == "win32":
            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        else:
            cap = cv2.VideoCapture(index)

        if not cap.isOpened():
            return None

        # Lista de propriedades do OpenCV para testar
        properties = {
            "CAP_PROP_FRAME_WIDTH": cv2.CAP_PROP_FRAME_WIDTH,
            "CAP_PROP_FRAME_HEIGHT": cv2.CAP_PROP_FRAME_HEIGHT,
            "CAP_PROP_FPS": cv2.CAP_PROP_FPS,
            "CAP_PROP_FOURCC": cv2.CAP_PROP_FOURCC,
            "CAP_PROP_FORMAT": cv2.CAP_PROP_FORMAT,
            "CAP_PROP_MODE": cv2.CAP_PROP_MODE,
            "CAP_PROP_BRIGHTNESS": cv2.CAP_PROP_BRIGHTNESS,
            "CAP_PROP_CONTRAST": cv2.CAP_PROP_CONTRAST,
            "CAP_PROP_SATURATION": cv2.CAP_PROP_SATURATION,
            "CAP_PROP_HUE": cv2.CAP_PROP_HUE,
            "CAP_PROP_GAIN": cv2.CAP_PROP_GAIN,
            "CAP_PROP_EXPOSURE": cv2.CAP_PROP_EXPOSURE,
            "CAP_PROP_CONVERT_RGB": cv2.CAP_PROP_CONVERT_RGB,
            "CAP_PROP_WHITE_BALANCE_BLUE_U": cv2.CAP_PROP_WHITE_BALANCE_BLUE_U,
            "CAP_PROP_RECTIFICATION": cv2.CAP_PROP_RECTIFICATION,
            "CAP_PROP_MONOCHROME": cv2.CAP_PROP_MONOCHROME,
            "CAP_PROP_SHARPNESS": cv2.CAP_PROP_SHARPNESS,
            "CAP_PROP_AUTO_EXPOSURE": cv2.CAP_PROP_AUTO_EXPOSURE,
            "CAP_PROP_GAMMA": cv2.CAP_PROP_GAMMA,
            "CAP_PROP_TEMPERATURE": cv2.CAP_PROP_TEMPERATURE,
            "CAP_PROP_TRIGGER": cv2.CAP_PROP_TRIGGER,
            "CAP_PROP_TRIGGER_DELAY": cv2.CAP_PROP_TRIGGER_DELAY,
            "CAP_PROP_WHITE_BALANCE_RED_V": cv2.CAP_PROP_WHITE_BALANCE_RED_V,
            "CAP_PROP_ZOOM": cv2.CAP_PROP_ZOOM,
            "CAP_PROP_FOCUS": cv2.CAP_PROP_FOCUS,
            "CAP_PROP_GUID": cv2.CAP_PROP_GUID,
            "CAP_PROP_ISO_SPEED": cv2.CAP_PROP_ISO_SPEED,
            "CAP_PROP_BACKLIGHT": cv2.CAP_PROP_BACKLIGHT,
            "CAP_PROP_PAN": cv2.CAP_PROP_PAN,
            "CAP_PROP_TILT": cv2.CAP_PROP_TILT,
            "CAP_PROP_ROLL": cv2.CAP_PROP_ROLL,
            "CAP_PROP_IRIS": cv2.CAP_PROP_IRIS,
            "CAP_PROP_BACKEND": cv2.CAP_PROP_BACKEND,
        }

        result = {}
        for name, prop_id in properties.items():
            try:
                value = cap.get(prop_id)
                if value != -1 and value != 0:  # Ignorar propriedades não suportadas
                    result[name] = value
            except Exception:
                pass

        # Tentar obter backend name
        try:
            backend = cap.getBackendName()
            result["BACKEND_NAME"] = backend
        except Exception:
            pass

        cap.release()
        return result

    except Exception as e:
        print(f"⚠️  Erro ao acessar câmera {index}: {e}")
        return None


def main():
    print("=" * 80)
    print("INVESTIGAÇÃO DE PROPRIEDADES DE CÂMERAS")
    print("=" * 80)
    print("\nTestando câmeras de índice 0 a 5...\n")

    cameras_found = []

    for i in range(6):
        print(f"\n{'=' * 80}")
        print(f"CÂMERA ÍNDICE {i}")
        print(f"{'=' * 80}")

        props = get_all_camera_properties(i)

        if props is None:
            print(f"❌ Não foi possível abrir câmera {i}")
            continue

        if not props:
            print(f"⚠️  Câmera {i} abriu mas não retornou propriedades")
            continue

        cameras_found.append((i, props))

        print(f"✅ Câmera {i} - {len(props)} propriedades encontradas:")
        for prop_name, value in sorted(props.items()):
            # Formatar valores especiais
            if prop_name == "CAP_PROP_FOURCC":
                fourcc_str = "".join([chr((int(value) >> 8 * i) & 0xFF) for i in range(4)])
                print(f"   {prop_name:35s} = {value:12.2f}  (FOURCC: '{fourcc_str}')")
            elif prop_name == "BACKEND_NAME":
                print(f"   {prop_name:35s} = {value}")
            else:
                print(f"   {prop_name:35s} = {value:12.2f}")

    # Comparação entre câmeras
    if len(cameras_found) >= 2:
        print("\n" + "=" * 80)
        print("COMPARAÇÃO ENTRE CÂMERAS")
        print("=" * 80)

        # Encontrar propriedades únicas
        all_props = set()
        for _, props in cameras_found:
            all_props.update(props.keys())

        print("\nPropriedades que DIFEREM entre as câmeras:")
        for prop_name in sorted(all_props):
            values = []
            for idx, props in cameras_found:
                val = props.get(prop_name, "N/A")
                values.append((idx, val))

            # Verificar se valores são diferentes
            unique_values = set(v for _, v in values if v != "N/A")
            if len(unique_values) > 1:
                print(f"\n   {prop_name}:")
                for idx, val in values:
                    if val != "N/A":
                        # Format based on type
                        if isinstance(val, str):
                            print(f"      Câmera {idx}: {val}")
                        else:
                            print(f"      Câmera {idx}: {val:.2f}")

    print("\n" + "=" * 80)
    print("CONCLUSÃO")
    print("=" * 80)
    print("\nPropriedades úteis para diferenciar câmeras:")
    print("   • CAP_PROP_FOURCC (codec)")
    print("   • CAP_PROP_EXPOSURE (tempo de exposição)")
    print("   • CAP_PROP_FOCUS (suporte a foco)")
    print("   • CAP_PROP_ZOOM (suporte a zoom)")
    print("   • BACKEND_NAME (backend usado)")


if __name__ == "__main__":
    main()
