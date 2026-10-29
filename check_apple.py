from apple_pickup import fetch_availability


def main():
    try:
        result = fetch_availability()
    except Exception as error:
        print(f"查询失败: {error}")
        return

    for store in result["stores"]:
        print(store["name"])
        for part in store["parts"]:
            print(
                f"  {part['title']} ({part['partNumber']}): "
                f"{part['status']} {part['quote']}"
            )


if __name__ == "__main__":
    main()
