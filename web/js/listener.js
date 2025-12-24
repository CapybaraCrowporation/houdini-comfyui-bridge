import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

var last_time = Date.now() / 1000;
const poll_time = 2000;

async function poll_messages() {
  const rep = await api.fetchApi("/sidefx_houdini/messages/get", { method: "POST", body: JSON.stringify({ since: last_time })} )
      .catch(
        (error) => {
          console.error("failed to poll comfyui")
          return null;
        }
      );
  if (rep === null) {
    return;
  }
  const data = await rep.json();

  const messages = data.messages;
  if (messages.length > 0) {
    for (var message of messages) {
      last_time = Math.max(last_time, message[0]);
      const command = message[1];
      const args = message[2];

      if (command == "create_loader") {
        const loader_name = args.image;
        const node = LiteGraph.createNode("LoadImage");
        node.title = "houdini import";
        node.widgets[0].value = loader_name;
        app.graph.add(node);

        node.pos = [app.canvas.visible_area[0] + app.canvas.visible_area[2]/2, app.canvas.visible_area[1] + app.canvas.visible_area[3]/2];
        
        console.log(node);
        console.log(app.graph);

      } else if (command == "refresh_all" || command == "refresh") {
        let checker = (n) => { return n.split("/").at(-1).startsWith("imgtemp"); };
        console.log(command, args.image)
        if (command == "refresh") {
          checker = (n) => { return n == args.image; };
        }
        
        for(let node of app.graph.nodes) {
          if (node.type != "LoadImage"
              || node.widgets.length == 0
              || node.widgets[0].name != "image"
              || !checker(node.widgets[0].value)) continue;

          if (node.imgs?.length != 1) {
            let img = new Image();
            let img_path = node.widgets[0].value;
            let [part1, part2] = img_path.split("/");
            if (part2 === undefined) {
              part2 = part1;
              part1 = "";
            }
            img.src = location.protocol + "//" + location.host + `/api/view?filename=${part2}&type=input&subfolder=${part1}&rand=0.0`
            node.imgs = [ img ];
          }

          // update img url rand param to force update
          let img_url = new URL(node.imgs[0].src);
          img_url.searchParams.set("rand", Math.random());
          node.imgs[0].src = img_url.toString();
        }
      } else {
        console.log(`ignoring unknown command "${command}"`);
      }
    }
  }
  
}


app.registerExtension({
  name: "org.xxx.houconnect",
  async setup() {
    setInterval(poll_messages, poll_time);
  }
})
