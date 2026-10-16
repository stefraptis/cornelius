import { redirect } from "next/navigation";

// The proxy sends signed-out users to /login; signed-in users land in the library.
export default function Home() {
  redirect("/library");
}
