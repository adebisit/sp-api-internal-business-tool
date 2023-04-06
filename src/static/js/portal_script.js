var sideBar = document.getElementById("menus-sidebar")
var openSideBar = document.getElementById("open-side-bar-btn")
var closeSideBar = document.getElementById("close-side-bar-btn")

openSideBar.onclick = function() {
    sideBar.style.width = "270px"
}

closeSideBar.onclick = function () {
    sideBar.style.width = "0px"
}


function formatToAccounting(amount, currency=""){
    return `${currency}${(amount).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,')}`;
}